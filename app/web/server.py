"""Web app cho mạng nhà: Hỏi (luồng trả lời LangGraph) + Tra cứu (đọc thẳng văn bản). docs/ui-context.md

Chạy:  bash scripts/run_web_demo.sh      (cần bash scripts/run_model_server.sh đang chạy)
Máy khác trong Wi-Fi nhà mở http://<IP của laptop>:8000 — tường lửa Windows phải mở cổng 8000 cho mạng Private.

Route chỉ kiểm đầu vào và gọi xuống app/answer, app/web/read_library — không gọi model, không viết SQL ở đây.
"""

import asyncio
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app import config
from app.answer.answer_graph import build_answer_graph
from app.answer.check_claim_support import load_nli_model
from app.answer.search_articles import provision_label
from app.web import read_library, read_performance

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
THREAD_COOKIE = "hoi_thoai"
MAX_QUESTION_CHARS = 2000
STEP_NAMES = {  # tên bước hiện cho người dùng trong lúc chờ
    "understand_question": "Đọc câu hỏi, lấy mốc thời gian",
    "reply_small_talk": "Trả lời lời chào",
    "look_up_definition": "Tra định nghĩa trong Điều \"Giải thích từ ngữ\"",
    "split_question": "Tách câu hỏi thành từng ý",
    "search_articles": "Tìm Điều luật liên quan",
    "add_referenced_articles": "Kéo thêm Điều được dẫn chiếu",
    "write_answer": "Viết câu trả lời",
    "check_citations": "Kiểm từng trích dẫn với văn bản gốc",
    "check_claim_support": "Kiểm câu kết luận có được căn cứ ủng hộ",
    "save_answer": "Lưu câu trả lời",
}
# Câu hỏi mẫu trên màn hình trống — bấm là hỏi.
SAMPLE_QUESTIONS = [
    "Nộp hồ sơ khai thuế quá thời hạn từ 61 đến 90 ngày thì bị phạt bao nhiêu?",
    "Thuế suất thuế thu nhập doanh nghiệp năm 2026 là bao nhiêu?",
    "Hộ kinh doanh có doanh thu bao nhiêu thì không phải nộp thuế?",
    "Mức thuế môn bài là bao nhiêu?",
]
# Khung debug (chỉ hiện trên chính laptop): ô nào của state sau mỗi bước — giống bản terminal.
DEBUG_FIELDS = {
    "understand_question": ["as_of_date", "as_of_source", "tax_types", "question_kind", "concept_term", "label_source",
                            "search_text"],
    "look_up_definition": ["articles"],
    "split_question": ["search_parts"],
    "search_articles": ["articles", "search_warning"],
    "add_referenced_articles": ["articles"],
    "write_answer": ["draft", "write_usage"],
    "check_citations": ["citations", "unverified_numbers", "has_cause"],
    "check_claim_support": ["claim_support", "support_score", "claim_unscored"],
    "save_answer": ["question_id"],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(config.DATABASE_CONNECTION) as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_answer_graph(checkpointer)
        # Mỗi lúc một câu hỏi: llama-server chạy -np 1, checkpointer dùng một kết nối (docs/code-standards.md).
        app.state.answer_lock = asyncio.Lock()
        log.info("Đang nạp model kiểm câu kết luận (guardrail g)…")
        await asyncio.to_thread(load_nli_model)
        log.info("Sẵn sàng.")
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def is_laptop(request: Request) -> bool:
    return request.client is not None and request.client.host in ("127.0.0.1", "::1")


def thread_id_of(request: Request) -> str | None:
    value = request.cookies.get(THREAD_COOKIE, "")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


# ---------------------------------------------------------------- Hỏi


@app.get("/")
async def home():
    return RedirectResponse("/hoi")


def vn_date(value) -> str:
    """'2026-12-31' hoặc date → '31/12/2026'."""
    text = str(value or "")[:10]
    return f"{text[8:10]}/{text[5:7]}/{text[:4]}" if len(text) == 10 else text


def set_thread_cookie(response, thread_id: str) -> None:
    response.set_cookie(THREAD_COOKIE, thread_id, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365)


async def shell_context(request: Request, page: str) -> dict:
    """Thanh bên có mặt trên mọi trang: danh sách cuộc hội thoại, cuộc đang mở."""
    return {"trang": page, "threads": await read_library.list_threads(), "current_thread": thread_id_of(request)}


def legacy_conclusion(text: str) -> str:
    """Câu trả lời lưu trước migration 008 chỉ có answers.text (bản terminal: mốc, kết luận, căn cứ) → lấy phần kết luận."""
    skipped = ("Áp dụng tại mốc", "KHÔNG CÓ CĂN CỨ", "- ", "⚠", "(")
    kept, inside_quote = [], False
    for line in text.splitlines():
        if line.startswith("- "):  # dòng căn cứ — đoạn trích có thể kéo sang các dòng sau tới dấu " đóng
            inside_quote = not line.rstrip().endswith('"')
        elif inside_quote:
            inside_quote = not line.rstrip().endswith('"')
        elif not line.startswith(skipped):
            kept.append(line)
    return "\n".join(kept).strip()


def turn_view(row: dict) -> dict:
    """Một lượt đã lưu → cùng dạng với kết quả trực tiếp, để trình duyệt dựng bằng một hàm."""
    citations = [citation_view(c) for c in row["citations"] or []]
    return {"cau_hoi": row["cau_hoi"], "giay": None, "ket_qua": {
        "chao_hoi": row["kind"] == "chao_hoi",
        "moc": vn_date(row["as_of_date"]), "ngu_canh": None, "co_can_cu": row["has_cause"],
        "ket_luan": row["ket_luan"] or legacy_conclusion(row["tra_loi"]), "con_so_chua_can_cu": [],
        "can_cu": [c for c in citations if c["trang_thai"] in ("dat", "bo_chu_ocr", "bo_cach_ly")],
        "so_trich_dan_bi_bo": sum(c["trang_thai"].startswith("bo_khong") or c["trang_thai"] == "bo_doan_khong_ton_tai"
                                  for c in citations),
    }}


@app.get("/hoi")
async def ask_page(request: Request, hoi_thoai: str = ""):
    if hoi_thoai:  # chọn một cuộc hội thoại ở thanh bên
        response = RedirectResponse("/hoi", status_code=303)
        try:
            set_thread_cookie(response, str(uuid.UUID(hoi_thoai)))
        except ValueError:
            pass
        return response
    thread_id = thread_id_of(request)
    turns = [turn_view(row) for row in await read_library.load_thread_turns(thread_id)] if thread_id else []
    context = await shell_context(request, "hoi")
    response = templates.TemplateResponse(request, "hoi.html", {
        **context, "turns": turns, "samples": SAMPLE_QUESTIONS, "show_debug": is_laptop(request)})
    if thread_id is None:
        set_thread_cookie(response, str(uuid.uuid4()))
    return response


@app.post("/hoi/moi")
async def new_conversation():
    response = RedirectResponse("/hoi", status_code=303)
    set_thread_cookie(response, str(uuid.uuid4()))
    return response


def citation_view(citation: dict) -> dict:
    """Một căn cứ để hiện: trích dẫn đã kiểm (có link tới đúng Điều) hoặc căn cứ chỉ có số hiệu + link."""
    # Căn cứ lưu theo định dạng cũ (không có document_id) thì không có link tới trang văn bản
    document_id, chunk_id = citation.get("document_id"), citation.get("chunk_id")
    link = (f"/van-ban/{document_id}#d-{chunk_id}" if chunk_id else f"/van-ban/{document_id}") if document_id else None
    return {"trang_thai": citation["trang_thai"], "vi_tri": citation.get("vi_tri"), "loai": citation.get("loai"),
            "so_hieu": citation.get("so_hieu"), "tieu_de": citation.get("tieu_de"), "trich_dan": citation.get("trich_dan"),
            "link": link,
            "can_kiem_hieu_luc": citation.get("can_kiem_hieu_luc", False),
            "het_hieu_luc": citation.get("het_hieu_luc")}


def answer_view(state: dict) -> dict:
    """Dữ liệu câu trả lời cho trình duyệt — trình duyệt dựng bằng textContent, không chèn HTML."""
    citations = [citation_view(c) for c in state.get("citations", [])]
    carried = state.get("label_source") == "luot_truoc"
    return {
        "chao_hoi": state.get("question_kind") == "chao_hoi",
        "moc": vn_date(state.get("as_of_date")),
        "ngu_canh": (" · ".join(state.get("tax_types") or []) + f" · mốc {vn_date(state.get('as_of_date'))}") if carried else None,
        "co_can_cu": state.get("has_cause", False),
        "ket_luan": (state.get("draft") or {}).get("ket_luan", ""),
        "con_so_chua_can_cu": state.get("unverified_numbers", []),
        "can_cu": [c for c in citations if c["trang_thai"] in ("dat", "bo_chu_ocr", "bo_cach_ly")],
        "so_trich_dan_bi_bo": sum(c["trang_thai"].startswith("bo_khong") or c["trang_thai"] == "bo_doan_khong_ton_tai"
                                  for c in citations),
    }


def debug_view(node: str, update: dict) -> dict:
    view = {}
    for field in DEBUG_FIELDS.get(node, []):
        value = update.get(field)
        if field == "articles":
            value = [f"{a['score']}  {a['loai']} {a['so_hieu']} — {provision_label(a['dieu_level'], a['dieu_so'])}. "
                     f"{(a['dieu_ten'] or '')[:60]}  [{', '.join(a.get('nguon', []))}]" for a in value or []]
        view[field] = value
    return view


async def model_is_running() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            return (await client.get(config.LLM_BASE_URL.removesuffix("/v1") + "/health")).status_code == 200
    except httpx.HTTPError:
        return False


@app.post("/api/hoi")
async def ask(request: Request):
    try:
        body = await request.json()
        question = str(body.get("cau_hoi", "")).strip()[:MAX_QUESTION_CHARS]
    except (ValueError, AttributeError):  # không phải JSON UTF-8 hợp lệ — trình duyệt luôn gửi đúng
        question = ""
    thread_id = thread_id_of(request) or str(uuid.uuid4())
    show_debug = is_laptop(request)

    async def events():
        def line(payload: dict) -> str:
            return json.dumps(payload, ensure_ascii=False, default=str) + "\n"

        if not question:
            yield line({"loi": "Câu hỏi trống."})
            return
        if not await model_is_running():
            yield line({"loi": "Model trên laptop chưa chạy (llama-server). Bật laptop lên và chạy "
                               "bash scripts/run_model_server.sh rồi hỏi lại."})
            return
        lock = request.app.state.answer_lock
        if lock.locked():
            yield line({"buoc": "cho", "ten": "Đang trả lời câu hỏi khác, chờ một chút…"})
        async with lock:
            state, started, written = {}, time.perf_counter(), ""
            run_config = {"configurable": {"thread_id": thread_id}}
            try:
                # "updates": xong từng bước; "custom": kết luận đang viết (write_answer) — chỉ gửi phần chữ mới thêm
                async for mode, chunk in request.app.state.graph.astream(
                        {"question": question, "thread_id": thread_id, "started_at": time.time()}, run_config,
                        stream_mode=["updates", "custom"], durability="async"):
                    if mode == "custom":
                        text = chunk.get("dang_viet", "")
                        yield line({"viet_them": text[len(written):]} if text.startswith(written)
                                   else {"dang_viet": text})
                        written = text
                        continue
                    for node, update in chunk.items():
                        state.update(update or {})
                        event = {"buoc": node, "ten": STEP_NAMES.get(node, node),
                                 "ms": round((time.perf_counter() - started) * 1000)}
                        if show_debug:
                            event["debug"] = debug_view(node, update or {})
                        yield line(event)
            except Exception as e:  # lỗi một câu hỏi không làm sập app
                log.exception("Lỗi khi trả lời")
                yield line({"loi": f"Lỗi khi trả lời: {type(e).__name__}. Thử hỏi lại."})
                return
            yield line({"ket_qua": answer_view(state), "giay": round(time.perf_counter() - started, 1)})

    return StreamingResponse(events(), media_type="application/x-ndjson")


# ---------------------------------------------------------------- Tra cứu


@app.get("/tra-cuu")
async def library_page(request: Request, q: str = "", con_hieu_luc: int = 0, cap: str = "", trang: int = 1):
    rank = int(cap) if cap.isdigit() and int(cap) in read_library.RANK_NAMES else None
    page = max(1, trang)
    documents, has_next = await read_library.list_documents(q[:200], bool(con_hieu_luc), rank, page)
    return templates.TemplateResponse(request, "tra_cuu.html", {
        **await shell_context(request, "tra_cuu"), "documents": documents, "has_next": has_next, "page": page,
        "q": q[:200], "con_hieu_luc": bool(con_hieu_luc), "cap": rank, "ranks": read_library.RANK_NAMES,
    })


@app.get("/hieu-nang")
async def performance_page(request: Request):
    return templates.TemplateResponse(request, "hieu_nang.html", {
        **await shell_context(request, "hieu_nang"), "p": await read_performance.load_performance()})


@app.get("/van-ban/{document_id}")
async def document_page(request: Request, document_id: str):
    try:
        document_id = str(uuid.UUID(document_id))
    except ValueError:
        return RedirectResponse("/tra-cuu")
    document = await read_library.load_document(document_id)
    if document is None:
        return RedirectResponse("/tra-cuu")
    return templates.TemplateResponse(request, "van_ban.html", {**await shell_context(request, "tra_cuu"), "d": document})


@app.get("/ban-goc/{document_id}")
async def original_file(document_id: str):
    """File gốc (PDF/Word) đã tải về; văn bản chỉ có HTML thì chuyển sang trang nguồn."""
    try:
        document_id = str(uuid.UUID(document_id))
    except ValueError:
        return RedirectResponse("/tra-cuu")
    document = await read_library.load_document(document_id)
    if document is None:
        return RedirectResponse("/tra-cuu")
    path = read_library.original_file(document)
    if path is None:
        return RedirectResponse(document["source_url"] or "/tra-cuu")
    return FileResponse(path, filename=path.name)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = uvicorn.Server(uvicorn.Config(app, host=config.WEB_HOST, port=config.WEB_PORT, log_level="info"))
    # uvicorn tự chọn ProactorEventLoop trên Windows — psycopg async cần SelectorEventLoop (docs/code-standards.md).
    asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)


if __name__ == "__main__":
    main()

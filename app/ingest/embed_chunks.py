"""Tính vector BGE-M3 cho các đoạn tìm kiếm chưa có vector (docs/architecture.md, Embedding).

Mỗi đoạn được gắn ngữ cảnh văn bản trước khi tính — cách Contextual Retrieval (Anthropic, 19/09/2024: gắn
50–100 token mô tả vị trí đoạn trong tài liệu làm tìm trượt giảm 35%). Ở đây ngữ cảnh lấy thẳng từ database,
không cần model: "Văn bản hợp nhất 113/VBHN-VPQH — Luật Thuế thu nhập doanh nghiệp…\\nĐiều 10. Thuế suất\\n<chữ>".

Nạp lại văn bản thì chunk đổi id → vector cũ tự xoá (ON DELETE CASCADE) → lần chạy sau tính lại.
Đổi GGUF hay cách gắn ngữ cảnh → đổi EMBEDDING_MODEL_VERSION (config) để tính lại toàn bộ.

Chạy (cần bash scripts/run_embedding_server.sh đang chạy; trong pipeline: công đoạn chunk_embeddings):
    python -m app.ingest.embed_chunks
    python -m app.ingest.embed_chunks --check   bài tự kiểm (không gọi server)
"""

import asyncio
import logging
import sys

import httpx
import psycopg

from app import config
from app.answer.call_local_model import embed_texts
from app.answer.search_articles import provision_label
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

BATCH_SIZE = 8
# BGE-M3 nhận tối đa 8.192 token; tiếng Việt qua tokenizer XLM-R khoảng 3–4 ký tự/token → cắt ở 12.000 ký tự cho
# an toàn. Điều dài hơn (456 Điều > 8.000 ký tự) chỉ phần đầu vào vector — phần sau vẫn tìm được bằng từ khoá.
MAX_CHARS = 12_000

PENDING_SQL = """
    select ch.id, ch.text, d.loai, d.so_hieu, d.tieu_de, p.level, p.so, p.ten
    from chunks ch
    join documents d on d.id = ch.document_id
    join provisions p on p.id = ch.dieu_provision_id
    where not exists (select 1 from embeddings e where e.chunk_id = ch.id
                      and e.model_name = %(model)s and e.model_version = %(version)s)
    order by ch.id"""


def embedding_text(loai: str | None, so_hieu: str | None, tieu_de: str | None, level: str, so: str,
                   ten: str | None, text: str) -> str:
    """Chữ đem tính vector: dòng ngữ cảnh văn bản + tên Điều/mục + chữ của đoạn, cắt ở MAX_CHARS."""
    document = " ".join(part for part in (loai, so_hieu) if part)
    header = f"{document} — {tieu_de}" if tieu_de else document
    heading = provision_label(level, so) + (f". {ten}" if ten else "")
    # Điều / mục: dòng đầu luôn là đề mục (split_articles) — đã có ở dòng heading, bỏ cho khỏi lặp. Đoạn cắt theo độ
    # dài ('doan') không có đề mục → giữ nguyên.
    body = text.split("\n", 1)[1] if level in ("dieu", "muc") and "\n" in text else text
    return f"{header}\n{heading}\n{body}"[:MAX_CHARS]


async def _embed_batch(rows: list[tuple]) -> list[list[float]]:
    texts = [embedding_text(*row[2:8], row[1]) for row in rows]
    try:
        return await embed_texts(texts)
    except httpx.HTTPStatusError:
        if len(rows) == 1:  # một đoạn quá dài so với batch của server → cắt đôi rồi thử lại
            return await embed_texts([texts[0][: len(texts[0]) // 2]])
        middle = len(rows) // 2
        return await _embed_batch(rows[:middle]) + await _embed_batch(rows[middle:])


def embed_pending_chunks() -> StageReport:
    report = StageReport("embedding")
    params = {"model": config.EMBEDDING_MODEL, "version": config.EMBEDDING_MODEL_VERSION}
    with psycopg.connect(config.DATABASE_CONNECTION, autocommit=True) as conn:
        rows = conn.execute(PENDING_SQL, params).fetchall()
        log.info("%d đoạn chưa có vector %s/%s", len(rows), *params.values())
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            try:
                vectors = asyncio.run(_embed_batch(batch))
            except httpx.ConnectError as e:
                raise RuntimeError("Server embedding chưa chạy — bash scripts/run_embedding_server.sh") from e
            except Exception as e:  # một lô lỗi không chặn lô khác
                report.fail(f"chunk {batch[0][0]}–{batch[-1][0]}", e, log)
                continue
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into embeddings (chunk_id, model_name, model_version, dim, vec) values (%s, %s, %s, %s, %s)"
                    " on conflict (chunk_id, model_name, model_version) do nothing",
                    [(row[0], params["model"], params["version"], len(vector), str(vector))
                     for row, vector in zip(batch, vectors)],
                )
            report.count("tinh_moi", len(batch))
            if (start // BATCH_SIZE) % 100 == 0:
                log.info("%d/%d đoạn", start + len(batch), len(rows))
        # Vector của phiên bản cũ không còn dùng → xoá cho khỏi phình bảng
        deleted = conn.execute("delete from embeddings where model_name = %(model)s and model_version <> %(version)s",
                               params).rowcount
        report.count("xoa_phien_ban_cu", deleted)
    return report


def self_check() -> None:
    text = embedding_text("Văn bản hợp nhất", "113/VBHN-VPQH", "Luật Thuế thu nhập doanh nghiệp", "dieu", "10",
                          "Thuế suất", "Điều 10. Thuế suất\n1. Thuế suất là 20%.")
    assert text == "Văn bản hợp nhất 113/VBHN-VPQH — Luật Thuế thu nhập doanh nghiệp\nĐiều 10. Thuế suất\n1. Thuế suất là 20%.", text
    text = embedding_text("Thông tư", "99/TC-TCT", None, "muc", "A.II", "MỨC THUẾ", "II. MỨC THUẾ\n1. Bậc 1")
    assert text.startswith("Thông tư 99/TC-TCT\nmục II phần A. MỨC THUẾ\n1. Bậc 1"), text
    assert len(embedding_text("Luật", "1", None, "dieu", "1", None, "x" * 50_000)) == MAX_CHARS
    text = embedding_text("Lệnh", "33-L/CTN", None, "doan", "1", None, "Việc công bố\nPháp lệnh thuế")
    assert text.endswith("Việc công bố\nPháp lệnh thuế"), "đoạn cắt theo độ dài giữ dòng đầu"
    print("PASS")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(embed_pending_chunks().summary())


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

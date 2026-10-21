"""Guardrail tất định cho câu trả lời (docs/danh-gia.md, mục 6):

a. mỗi đoạn trích phải khớp từng chữ với Điều đã lưu — không khớp thì bỏ (quy tắc bất biến số 1);
   chỉ chấp nhận khác nhau về khoảng trắng (xuống dòng, nhiều dấu cách);
b. trích dẫn phải thuộc một đoạn đã tìm cho câu hỏi này (model chỉ được trỏ số đoạn);
c. mọi con số trong kết luận phải có trong một đoạn trích đã qua kiểm — không thì gắn cờ;
e. chữ OCR không bao giờ được trích — chỉ hiện số hiệu + link (quy tắc bất biến số 2).
"""

import re

import psycopg

from app import config
from app.answer.search_articles import load_chunk_texts

LEVEL_NAMES = {"diem": "điểm", "khoan": "khoản", "dieu": "Điều"}
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*\s*%?")


def collapse_whitespace(text: str) -> tuple[str, list[int]]:
    """Gộp mọi khoảng trắng liên tiếp thành một dấu cách; trả kèm vị trí gốc của từng ký tự."""
    chars, origins = [], []
    previous_was_space = False
    for position, char in enumerate(text):
        if char.isspace():
            if previous_was_space:
                continue
            chars.append(" ")
            previous_was_space = True
        else:
            chars.append(char)
            previous_was_space = False
        origins.append(position)
    return "".join(chars), origins


def find_quote(quote: str, article_text: str) -> int | None:
    """Vị trí bắt đầu (trong chữ gốc) của đoạn trích, hoặc None nếu không khớp."""
    quote = quote.strip().strip('"“”')
    if len(quote) < 10:  # quá ngắn thì khớp ở đâu cũng được — không coi là căn cứ
        return None
    position = article_text.find(quote)
    if position >= 0:
        return position
    collapsed_text, origins = collapse_whitespace(article_text)
    collapsed_quote, _ = collapse_whitespace(quote)
    position = collapsed_text.find(collapsed_quote)
    return origins[position] if position >= 0 else None


async def label_position(conn: psycopg.AsyncConnection, chunk_id: int, position: int) -> str:
    """'điểm a khoản 4 Điều 6' — từ bảng chunk_positions, vùng nhỏ nhất chứa vị trí trích."""
    cursor = await conn.execute(
        "select level, so, char_start, char_end from chunk_positions "
        "where chunk_id = %s and char_start <= %s and %s < char_end order by char_end - char_start",
        (chunk_id, position, position),
    )
    spans = await cursor.fetchall()
    order = {"diem": 0, "khoan": 1, "dieu": 2}
    parts = {}
    for level, so, _, _ in spans:
        parts.setdefault(level, so)
    return " ".join(f"{LEVEL_NAMES[level]} {parts[level]}" for level in sorted(parts, key=order.get))


async def check_citations(state: dict) -> dict:
    """Node LangGraph. Chỉ đọc database, không ghi."""
    draft = state["draft"]
    articles = state.get("articles") or []
    texts = await load_chunk_texts([a["chunk_id"] for a in articles])
    citations = []
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        for item in draft.get("can_cu", []):
            number = item.get("doan")
            if not isinstance(number, int) or not 1 <= number <= len(articles):
                citations.append({**item, "trang_thai": "bo_doan_khong_ton_tai"})
                continue
            article = articles[number - 1]
            if article["text_origin"] == "ocr":
                citations.append({**item, "trang_thai": "bo_chu_ocr", "so_hieu": article["so_hieu"],
                                  "link": article["source_url"]})
                continue
            position = find_quote(item["trich_dan"], texts[article["chunk_id"]])
            if position is None:
                citations.append({**item, "trang_thai": "bo_khong_khop", "so_hieu": article["so_hieu"]})
                continue
            label = await label_position(conn, article["chunk_id"], position)
            # chunk_id + vi_tri_ky_tu: guardrail g (check_claim_support) lấy cả khoản chứa đoạn trích làm ngữ cảnh
            citations.append({**item, "trang_thai": "dat", "so_hieu": article["so_hieu"], "loai": article["loai"],
                              "vi_tri": label, "link": article["source_url"],
                              "chunk_id": article["chunk_id"], "vi_tri_ky_tu": position})

    verified_quotes = " ".join(c["trich_dan"] for c in citations if c["trang_thai"] == "dat")
    unverified_numbers = [
        n.strip() for n in NUMBER_PATTERN.findall(draft.get("ket_luan", ""))
        if n.strip().rstrip("%").strip() not in verified_quotes
    ]
    has_cause = draft.get("co_can_cu", False) and any(c["trang_thai"] == "dat" for c in citations)
    return {
        "citations": citations,
        "unverified_numbers": unverified_numbers,
        "has_cause": has_cause,
        "answer_text": render_answer(state, draft, citations, unverified_numbers, has_cause),
    }


def render_answer(state: dict, draft: dict, citations: list[dict], unverified_numbers: list[str],
                  has_cause: bool) -> str:
    """Bản chữ cho terminal. Giao diện web sẽ trình bày từ cùng dữ liệu này."""
    lines = [f"Áp dụng tại mốc: {state['as_of_date']}"]
    if not has_cause:
        lines.append("KHÔNG CÓ CĂN CỨ trong dữ liệu đã tìm.")
    lines.append(draft.get("ket_luan", ""))
    if unverified_numbers:
        lines.append(f"⚠ Con số chưa có căn cứ trong đoạn trích: {', '.join(unverified_numbers)}")
    for citation in citations:
        if citation["trang_thai"] == "dat":
            lines.append(f"- {citation['vi_tri']} {citation['loai']} {citation['so_hieu']}: \"{citation['trich_dan']}\"")
        elif citation["trang_thai"] == "bo_chu_ocr":
            lines.append(f"- {citation['so_hieu']} (bản scan — xem bản gốc: {citation['link']})")
    dropped = sum(c["trang_thai"].startswith("bo_khong") or c["trang_thai"] == "bo_doan_khong_ton_tai"
                  for c in citations)
    if dropped:
        lines.append(f"({dropped} trích dẫn bị bỏ vì không khớp nguyên văn)")
    return "\n".join(lines)

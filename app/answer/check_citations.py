"""Guardrail tất định cho câu trả lời (docs/danh-gia.md, mục 6):

a. mỗi đoạn trích phải khớp từng chữ với Điều đã lưu — không khớp thì bỏ (quy tắc bất biến số 1);
   chỉ chấp nhận khác nhau về khoảng trắng (xuống dòng, nhiều dấu cách);
b. trích dẫn phải thuộc một đoạn đã tìm cho câu hỏi này (model chỉ được trỏ số đoạn); ghi nhầm số đoạn mà chữ khớp
   nguyên văn đúng một đoạn khác trong danh sách → đổi về đoạn đó (model hay lẫn số đoạn với số Điều khi có nhiều đoạn);
c. mọi con số trong kết luận phải có trong một đoạn trích đã qua kiểm — không thì gắn cờ; trừ số đã có trong câu hỏi,
   năm của mốc thời gian, số trong số hiệu văn bản được dẫn, số của chỗ dẫn ("khoản 1 Điều 9", "19/VBHN-BTC"), số thứ tự
   đầu dòng (không phải thông tin lấy từ luật);
e. chữ OCR không bao giờ được trích — chỉ hiện số hiệu + link (quy tắc bất biến số 2).

Bài tự kiểm: python -m app.answer.check_citations
"""

import re

import psycopg

from app import config
from app.answer.search_articles import expiry_note, load_chunk_texts, provision_label

NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*\s*%?")
# Số của chỗ dẫn, không phải dữ kiện: "khoản 1 Điều 9", "điểm a", "19/VBHN-BTC", "252/2026/NĐ-CP", "1. " đầu dòng.
# Số hiệu phải có chữ in hoa sau dấu "/" — ngày "1/7/2026" vẫn phải có căn cứ.
REFERENCE_NUMBERS = re.compile(
    r"\b(?:[Đđ]iều|[Kk]hoản|[Đđ]iểm|[Cc]hương|[Mm]ục|[Pp]hụ lục)\s+[0-9IVXL]+[a-zđ]?\b"
    r"|\b\d+(?:/\d{4})?/[0-9]*[A-ZĐ][A-ZĐa-zđ0-9-]*|^\s*\d+\.\s", re.MULTILINE)


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
    order = {"diem": 0, "khoan": 1, "dieu": 2, "muc": 2, "doan": 2}
    parts = {}
    for level, so, _, _ in spans:
        parts.setdefault(level, so)
    return " ".join(provision_label(level, parts[level]) for level in sorted(parts, key=order.get))


def numbers_without_basis(conclusion: str, verified_quotes: str, known: list[str]) -> list[str]:
    """Con số trong kết luận không có trong đoạn trích đã kiểm. `known`: chữ mà con số trong đó không cần căn cứ —
    câu hỏi, năm của mốc, số hiệu văn bản được dẫn ("năm 2026", "25/2026/VBHN-BTC" → 2026). So khớp nguyên số:
    "1" trong câu hỏi không miễn "15"."""
    known_numbers = {n.strip() for text in known for n in NUMBER_PATTERN.findall(text)}
    return [n.strip() for n in NUMBER_PATTERN.findall(REFERENCE_NUMBERS.sub(" ", conclusion))
            if n.strip().rstrip("%").strip() not in verified_quotes and n.strip() not in known_numbers]


def find_passage(quote: str, number, articles: list[dict], texts: dict[int, str]) -> int | None:
    """Số đoạn chứa trích dẫn: đoạn model ghi nếu khớp; không thì đoạn khác DUY NHẤT khớp nguyên văn; không thì None."""
    if isinstance(number, int) and 1 <= number <= len(articles) and \
            find_quote(quote, texts[articles[number - 1]["chunk_id"]]) is not None:
        return number
    homes = [n for n, article in enumerate(articles, start=1) if find_quote(quote, texts[article["chunk_id"]]) is not None]
    return homes[0] if len(homes) == 1 else None


async def check_citations(state: dict) -> dict:
    """Node LangGraph. Chỉ đọc database, không ghi."""
    draft = state["draft"]
    articles = state.get("articles") or []
    texts = await load_chunk_texts([a["chunk_id"] for a in articles])
    citations = []
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        for item in draft.get("can_cu", []):
            number = item.get("doan")
            if (found := find_passage(item["trich_dan"], number, articles, texts)) not in (None, number):
                item = {**item, "doan": found, "doan_model_ghi": number}
                number = found
            if not isinstance(number, int) or not 1 <= number <= len(articles):
                citations.append({**item, "trang_thai": "bo_doan_khong_ton_tai"})
                continue
            article = articles[number - 1]
            if article["text_origin"] == "ocr":
                citations.append({**item, "trang_thai": "bo_chu_ocr", "so_hieu": article["so_hieu"], "tieu_de": article.get("tieu_de"), "document_id": article.get("document_id"),
                                  "link": article["source_url"]})
                continue
            if article.get("ly_do_cach_ly"):  # chữ chưa qua kiểm chất lượng — như OCR: số hiệu + link, không trích
                citations.append({**item, "trang_thai": "bo_cach_ly", "so_hieu": article["so_hieu"], "tieu_de": article.get("tieu_de"), "document_id": article.get("document_id"),
                                  "link": article["source_url"], "ly_do": article["ly_do_cach_ly"]})
                continue
            position = find_quote(item["trich_dan"], texts[article["chunk_id"]])
            if position is None:
                citations.append({**item, "trang_thai": "bo_khong_khop", "so_hieu": article["so_hieu"]})
                continue
            label = await label_position(conn, article["chunk_id"], position)
            # chunk_id + vi_tri_ky_tu: guardrail g (check_claim_support) lấy cả khoản chứa đoạn trích làm ngữ cảnh
            citations.append({**item, "trang_thai": "dat", "so_hieu": article["so_hieu"], "tieu_de": article.get("tieu_de"), "document_id": article.get("document_id"), "loai": article["loai"],
                              "vi_tri": label, "link": article["source_url"],
                              "can_kiem_hieu_luc": bool(article.get("can_kiem_hieu_luc")),
                              "het_hieu_luc": expiry_note(article["het_hieu_luc"]) if article.get("het_hieu_luc") else None,
                              "chunk_id": article["chunk_id"], "vi_tri_ky_tu": position})

    verified = [c for c in citations if c["trang_thai"] == "dat"]
    unverified_numbers = numbers_without_basis(
        draft.get("ket_luan", ""), " ".join(c["trich_dan"] for c in verified),
        known=[state["question"], str(state["as_of_date"])[:4]] + [c["so_hieu"] or "" for c in verified])
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
            warning = " [cần kiểm hiệu lực — văn bản cũ, cổng ghi còn hiệu lực]" if citation.get("can_kiem_hieu_luc") else ""
            warning = f" [{citation['het_hieu_luc']}]" if citation.get("het_hieu_luc") else warning
            lines.append(f"- {citation['vi_tri']} {citation['loai']} {citation['so_hieu']}{warning}: \"{citation['trich_dan']}\"")
        elif citation["trang_thai"] == "bo_chu_ocr":
            lines.append(f"- {citation['so_hieu']} (bản scan — xem bản gốc: {citation['link']})")
        elif citation["trang_thai"] == "bo_cach_ly":
            lines.append(f"- {citation['so_hieu']} (chữ đang chờ kiểm tay, chưa trích được — xem bản gốc: {citation['link']})")
    dropped = sum(c["trang_thai"].startswith("bo_khong") or c["trang_thai"] == "bo_doan_khong_ton_tai"
                  for c in citations)
    if dropped:
        lines.append(f"({dropped} trích dẫn bị bỏ vì không khớp nguyên văn)")
    return "\n".join(lines)


def self_check() -> None:
    quote = "Hộ kinh doanh có mức doanh thu năm từ 01 tỷ đồng trở xuống thuộc đối tượng không chịu thuế"
    known = ["Năm 2026 hộ kinh doanh có doanh thu bao nhiêu thì không phải nộp thuế?", "2026", "25/2026/VBHN-BTC"]
    conclusion = "Nếu hộ kinh doanh có doanh thu năm 2026 từ 01 tỷ đồng trở xuống thì không phải nộp thuế"
    assert numbers_without_basis(conclusion, quote, known) == [], "năm của câu hỏi / mốc không cần căn cứ"
    assert numbers_without_basis("Áp dụng từ năm 2027", quote, known) == ["2027"], "năm khác vẫn phải có căn cứ"
    assert numbers_without_basis("Phạt 15 triệu", "phạt 5 triệu", ["khoản 1"]) == ["15"], "so khớp nguyên số"
    conclusion = "1. Chi phí: theo khoản 1 Điều 9 của 19/VBHN-BTC và Điều 12 Nghị định 252/2026/NĐ-CP, phạt 20%"
    assert numbers_without_basis(conclusion, "Phạt 20% số tiền thuế", []) == [], "số của chỗ dẫn không cần căn cứ"
    assert numbers_without_basis("hạn nộp là 1/7/2026", "", []) == ["1/7/2026"] or \
        numbers_without_basis("hạn nộp là 1/7/2026", "", []) == ["1", "7", "2026"], "ngày vẫn phải có căn cứ"
    articles = [{"chunk_id": 1}, {"chunk_id": 2}]
    texts = {1: "Điều 9. Chi phí được trừ khi tính thuế", 2: "1. Phạt 20% số tiền thuế khai thiếu"}
    assert find_passage("Phạt 20% số tiền thuế khai thiếu", 16, articles, texts) == 2, "model ghi nhầm số đoạn"
    assert find_passage("Phạt 20% số tiền thuế khai thiếu", 2, articles, texts) == 2
    assert find_passage("câu không có ở đâu cả trong văn bản", 1, articles, texts) is None
    assert find_quote("Thuế suất là 20%.", "Điều 10.\n1. Thuế   suất\nlà 20%.") == 12, "khoảng trắng khác nhau vẫn khớp"
    assert find_quote("ngắn", "rất ngắn") is None
    print("PASS")


if __name__ == "__main__":
    self_check()

"""Kéo thêm Điều mà các Điều tìm được dẫn chiếu tới trong cùng văn bản (docs/architecture.md, Model AI).

27% số đoạn có câu kiểu "theo quy định tại khoản 2 Điều 9 Luật này". Chỉ đưa Điều đang có thì model không thấy
Điều 9 → trả lời thiếu nửa quy định. Dẫn chiếu tìm bằng quy tắc, không gọi model:
- nhận "Điều 9", "Điều 9 Luật này", "khoản 2 Điều 9 của Nghị định này" — cùng văn bản;
- bỏ "Điều 9 Luật Quản lý thuế", "Điều 9 Nghị định số 126/2020/NĐ-CP" — văn bản khác;
- bỏ mọi dẫn chiếu trong văn bản sửa đổi: "sửa đổi khoản 2 Điều 9" là Điều của văn bản bị sửa, không phải của nó.
Điều thêm vào cuối danh sách, trích dẫn từ nó vẫn qua đủ guardrail ở check_citations.

Chạy bài tự kiểm: python -m app.answer.add_referenced_articles --check
"""

import re

import psycopg
from psycopg.rows import dict_row

from app import config
from app.answer.search_articles import FROM_SQL, SELECT_COLUMNS, load_chunk_texts
from app.answer.write_answer import MAX_CHARS_PER_ARTICLE

MAX_REFERENCED = 2  # vừa ngữ cảnh 16K token cùng các Điều tìm được (write_answer.CONTEXT_CHAR_BUDGET)
MAX_CEASING = 1  # khoản tuyên bố chấm dứt khoản thu — một khoản ngắn, đủ trả lời "còn phải nộp không"
SOURCE_LABEL = re.compile(r"(?:khoản (?P<khoan>\S+) )?Điều (?P<dieu>\S+)")  # chỗ tuyên bố: 'khoản 7 Điều 10'
# Khoản tuyên bố chấm dứt khoản thu (docs/architecture.md, Khoản thu bị chấm dứt): đủ cột như kết quả tìm kiếm.
CEASING_SQL = f"""
    select {SELECT_COLUMNS}, kp.char_start, kp.char_end
    {FROM_SQL}
    left join chunk_positions kp on kp.chunk_id = ch.id and kp.level = 'khoan' and kp.so = %(khoan)s
    where d.id = %(document_id)s::uuid and p.level = 'dieu' and p.so = %(dieu)s
    order by kp.char_start nulls last
    limit 1"""
REFERENCE = re.compile(r"(?:\bkhoản\s+(\d+)\s+(?:của\s+)?)?\bĐiều\s+(\d+[a-zđ]?)\b(?![./]\d)")
DOCUMENT_TYPE = re.compile(r"\b(?:Bộ luật|Luật|Pháp lệnh|Nghị quyết|Nghị định|Quyết định|Thông tư|Hiến pháp|Văn bản"
                           r"|Hiệp định|Công ước|Điều ước|Quy chế|Quy định)\b(\s+liên tịch)?(\s+này\b)?")
SENTENCE_END = re.compile(r"\.(?!\d)|\n")
# Điều của quy chế ban hành kèm theo lưu so = "QC1.5" (save_to_database); "Điều 3" trong đó là Điều 3 của quy chế.
ATTACHED_PART = re.compile(r"(QC\d+\.)(.+)")

# Văn bản sửa đổi: có quan hệ sua_doi (link_consolidated_documents) hoặc tên văn bản nói "sửa đổi".
AMENDING_DOCUMENTS_SQL = """
    select d.id::text from documents d
    where d.id::text = any(%(ids)s)
      and (exists (select 1 from document_relations r where r.from_doc = d.id and r.relation_type = 'sua_doi')
           or lower(f_unaccent(coalesce(d.tieu_de, ''))) like '%%sua doi%%')"""
TARGET_SQL = """
    select ch.id as chunk_id, p.level as dieu_level, p.so as dieu_so, p.ten as dieu_ten,
           kp.char_start, kp.char_end
    from chunks ch
    join provisions p on p.id = ch.dieu_provision_id
    left join chunk_positions kp on kp.chunk_id = ch.id and kp.level = 'khoan' and kp.so = %(khoan)s
    where ch.document_id = %(document_id)s::uuid and p.level = 'dieu' and p.so = %(dieu)s
    order by kp.char_start nulls last
    limit 1"""


def find_internal_references(text: str, own_number: str | None) -> list[tuple[str | None, str]]:
    """(khoản hoặc None, số Điều) theo thứ tự xuất hiện, bỏ trùng; bỏ dẫn chiếu sang văn bản khác và chính Điều này."""
    found: list[tuple[str | None, str]] = []
    for match in REFERENCE.finditer(text):
        clause, article = match.group(1), match.group(2)
        if article == own_number:
            continue
        # Tên văn bản đầu tiên sau dẫn chiếu, trong cùng câu, quyết định: "… này" → cùng văn bản; tên khác → văn bản
        # khác. Xét tới hết câu, không dừng ở ";": danh sách "khoản 3 Điều 24; điểm b khoản 3 Điều 25 Nghị định số
        # 125/2020" thuộc văn bản ở cuối danh sách. Nhầm thì chỉ bỏ sót dẫn chiếu, không kéo nhầm Điều.
        rest = SENTENCE_END.split(text[match.end():match.end() + 400], maxsplit=1)[0]
        named = DOCUMENT_TYPE.search(rest)
        if named and not named.group(2):
            continue
        if (clause, article) not in found:
            found.append((clause, article))
    return found


def attached_part(number: str | None) -> tuple[str, str | None]:
    """'QC1.5' → ('QC1.', '5'); '13' → ('', '13')."""
    if number and (match := ATTACHED_PART.fullmatch(number)):
        return match[1], match[2]
    return "", number


async def ceasing_articles(conn, sources: list[dict], as_of, have: set[int]) -> list[dict]:
    """Khoản tuyên bố chấm dứt khoản thu (search_articles.ceased_sources), mỗi chỗ tuyên bố một lần."""
    added = []
    for source in sources[:MAX_CEASING]:
        match = SOURCE_LABEL.fullmatch(source["vi_tri"])
        if match is None:
            continue
        cursor = await conn.execute(CEASING_SQL, {"document_id": source["document_id"], "dieu": match["dieu"],
                                                  "khoan": match["khoan"] or "", "as_of": as_of})
        row = await cursor.fetchone()
        if row is None or row["chunk_id"] in have:
            continue
        have.add(row["chunk_id"])
        start, end = row.pop("char_start"), row.pop("char_end")
        row.pop("uu_tien")
        span = (start, end) if start is not None else None
        added.append({**row, "score": 0.0, "nguon": ["cham_dut"],
                      "dan_chieu": {"tu_doan": None, "khoan": match["khoan"] if span else None, "vi_tri": span}})
    return added


async def add_referenced_articles(state: dict) -> dict:
    """Node LangGraph: thêm vào cuối `articles` tối đa MAX_REFERENCED Điều được dẫn chiếu, và khoản tuyên bố chấm dứt
    khoản thu của các văn bản tìm được."""
    articles = state.get("articles") or []
    native = [a for a in articles if a["text_origin"] == "native"]  # chữ OCR không trích được — dẫn chiếu cũng bỏ
    texts = await load_chunk_texts([a["chunk_id"] for a in native])
    have = {a["chunk_id"] for a in articles}
    added: list[dict] = []
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        added += await ceasing_articles(conn, state.get("ceased_sources") or [], state["as_of_date"], have)
        cursor = await conn.execute(AMENDING_DOCUMENTS_SQL, {"ids": [a["document_id"] for a in native]})
        amending = {row["id"] for row in await cursor.fetchall()}
        for article in native:
            if article["document_id"] in amending:
                continue
            number = articles.index(article) + 1
            prefix, own = attached_part(article["dieu_so"] if article["dieu_level"] == "dieu" else None)
            for clause, target in find_internal_references(texts[article["chunk_id"]][:MAX_CHARS_PER_ARTICLE], own):
                if sum("dan_chieu tu" in " ".join(a["nguon"]) for a in added) >= MAX_REFERENCED:
                    break
                cursor = await conn.execute(TARGET_SQL, {"document_id": article["document_id"], "dieu": prefix + target,
                                                         "khoan": clause or ""})
                row = await cursor.fetchone()
                if row is None or row["chunk_id"] in have:
                    continue
                have.add(row["chunk_id"])
                span = (row["char_start"], row["char_end"]) if clause and row["char_start"] is not None else None
                added.append({
                    **{key: article[key] for key in ("document_id", "so_hieu", "tieu_de", "loai", "text_origin",
                                                     "source_url", "can_kiem_hieu_luc", "het_hieu_luc", "ly_do_cach_ly")},
                    "chunk_id": row["chunk_id"], "dieu_level": row["dieu_level"], "dieu_so": row["dieu_so"],
                    "dieu_ten": row["dieu_ten"], "score": 0.0, "nguon": [f"dan_chieu tu [{number}]"],
                    "dan_chieu": {"tu_doan": number, "khoan": clause if span else None, "vi_tri": span},
                })
    return {"articles": articles + added} if added else {}


def self_check() -> None:
    check = find_internal_references
    assert check("Mức phạt quy định tại khoản 2 Điều 9 Luật này.", "13") == [("2", "9")]
    assert check("theo quy định tại Điều 9 của Nghị định này", "13") == [(None, "9")]
    assert check("thực hiện theo khoản 3 Điều 5 Thông tư liên tịch này", None) == [("3", "5")]
    assert check("Đối tượng quy định tại Điều 4 và khoản 1 Điều 6.", "10") == [(None, "4"), ("1", "6")]
    assert check("theo Điều 9 Luật Quản lý thuế số 38/2019/QH14", "13") == [], "văn bản khác"
    assert check("quy định tại Điều 9, Điều 10 Nghị định số 126/2020/NĐ-CP", "13") == [], "văn bản khác cuối vế câu"
    assert check("Điều 13. Xử phạt\n1. Phạt theo Điều 13 và Điều 13", "13") == [], "chính Điều này"
    assert check("theo khoản 2 Điều 9; khoản 2 Điều 9 Luật này", "1") == [("2", "9")], "bỏ trùng"
    assert check("Điều 5a được bổ sung", "1") == [(None, "5a")]
    assert check("Điều 9.2 của phụ lục", "1") == [], "không phải số Điều"
    assert check("theo quy định tại Điều 9 của Hiệp định 2010", "23") == []
    assert check("tại khoản 3 Điều 24; điểm b khoản 3 Điều 25 Nghị định này.", "8") == [("3", "24"), ("3", "25")]
    assert check("tại khoản 3 Điều 24; điểm b khoản 3 Điều 25 Nghị định số 125/2020/NĐ-CP.", "8") == []
    assert check("theo khoản 1 Điều 16 Thông tư này và văn bản nhận lại hàng", "68") == [("1", "16")]
    assert attached_part("QC1.5") == ("QC1.", "5") and attached_part("13") == ("", "13")
    print("PASS")


if __name__ == "__main__":
    self_check()

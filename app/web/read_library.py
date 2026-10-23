"""Đọc dữ liệu cho trang Tra cứu (docs/ui-context.md, màn hình Tra cứu). Chỉ đọc, không ghi.

Nhãn hiệu lực dùng chung biểu thức với tìm kiếm (search_articles.NEEDS_VALIDITY_CHECK_SQL) — hai nơi không lệch nhau.
"""

import json
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app import config
from app.answer.search_articles import (
    NEEDS_VALIDITY_CHECK_SQL, REPLACED_BY_SQL, YEAR_ONLY_END_SQL, expiry_note, provision_label,
)
from app.ingest import read_attachments

PAGE_SIZE = 50
# Thứ bậc văn bản để xếp danh sách (docs/thu-bac-van-ban.md): hợp nhất trước, công văn cuối.
RANK_SQL = """case when d.doc_group = 'VBHN' then 0
                   when d.loai in ('Hiến pháp') then 1
                   when d.loai in ('Luật', 'Bộ luật') then 2
                   when d.loai like 'Nghị quyết%%' or d.loai = 'Pháp lệnh' then 3
                   when d.loai = 'Nghị định' then 4
                   when d.loai like 'Quyết định%%' then 5
                   when d.loai like 'Thông tư%%' then 6
                   when d.loai = 'Công văn' or d.doc_group = 'CV' then 9
                   else 7 end"""
RANK_NAMES = {0: "Văn bản hợp nhất", 1: "Hiến pháp", 2: "Luật", 3: "Nghị quyết, pháp lệnh", 4: "Nghị định",
              5: "Quyết định", 6: "Thông tư", 7: "Văn bản khác", 9: "Công văn — hướng dẫn, không phải văn bản quy phạm"}
DOCUMENT_COLUMNS = f"""
    d.id::text as id, d.so_hieu, d.tieu_de, d.loai, d.doc_group, d.co_quan, d.ngay_ban_hanh, d.eff_from, d.eff_to,
    d.eff_status_code, d.text_origin, d.source_url, d.raw_path, {RANK_SQL} as cap,
    {NEEDS_VALIDITY_CHECK_SQL} as can_kiem_hieu_luc,
    {REPLACED_BY_SQL} as het_hieu_luc,
    {YEAR_ONLY_END_SQL} as het_theo_nam,
    qd.reasons as ly_do_cach_ly"""

LIST_SQL = f"""
    select {DOCUMENT_COLUMNS}
    from documents d
    left join quarantined_documents qd on qd.document_id = d.id
    where (%(q)s = '' or d.so_hieu ilike '%%' || %(q)s || '%%' or d.tieu_de ilike '%%' || %(q)s || '%%'
           or f_unaccent(coalesce(d.tieu_de, '')) ilike '%%' || f_unaccent(%(q)s) || '%%')
      and (not %(in_force)s or ({YEAR_ONLY_END_SQL} is null or {YEAR_ONLY_END_SQL} > %(as_of)s))
      and (not %(in_force)s or (coalesce(d.eff_status_code, '') <> 'HHL'
                                and (d.eff_to is null or d.eff_to > %(as_of)s)
                                and (d.eff_from is null or d.eff_from <= %(as_of)s)))
      and (%(rank)s::int is null or {RANK_SQL} = %(rank)s::int)
    order by cap, d.ngay_ban_hanh desc nulls last
    limit {PAGE_SIZE + 1} offset %(offset)s"""


def labels(row: dict) -> list[tuple[str, str]]:
    """(chữ nhãn, loại nhãn cho CSS) — nhãn luôn có chữ (docs/ui-context.md, Icon)."""
    found = []
    today = date.today()
    if row["eff_status_code"] == "HHL" or (row["eff_to"] and row["eff_to"] <= today):
        found.append(("Hết hiệu lực" + (f" từ {row['eff_to']:%d/%m/%Y}" if row["eff_to"] else ""), "expired"))
    elif row["eff_status_code"] == "HHL1P":
        found.append(("Hết hiệu lực một phần", "expired"))
    if row["het_theo_nam"] and row["het_theo_nam"] <= today:
        found.append((f"Hết hiệu lực — chỉ áp dụng trong năm {row['het_theo_nam'].year - 1} "
                      "(cổng chưa ghi ngày hết hiệu lực)", "expired"))
    if row["het_hieu_luc"]:
        found.append((expiry_note(row["het_hieu_luc"]), "expired"))
    elif row["can_kiem_hieu_luc"]:
        found.append(("Cần kiểm hiệu lực — văn bản cũ, cổng ghi còn hiệu lực", "check"))
    if row["loai"] == "Công văn" or row["doc_group"] == "CV":
        found.append(("Công văn — không phải văn bản quy phạm", "guidance"))
    if row["text_origin"] == "ocr":
        found.append(("Bản scan / PDF — chữ chỉ để tìm, xem bản gốc", "ocr"))
    elif row["text_origin"] == "none":
        found.append(("Chưa đọc được chữ — xem bản gốc", "ocr"))
    if row["ly_do_cach_ly"]:
        found.append(("Chữ đang chờ kiểm tay", "check"))
    return found


async def list_documents(q: str, in_force: bool, rank: int | None, page: int) -> tuple[list[dict], bool]:
    """Một trang danh sách và có trang sau hay không."""
    params = {"q": q.strip(), "in_force": in_force, "as_of": date.today(), "rank": rank,
              "offset": (page - 1) * PAGE_SIZE}
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        rows = await (await conn.execute(LIST_SQL, params)).fetchall()
    for row in rows:
        row["nhan"] = labels(row)
        row["ten_cap"] = RANK_NAMES[row["cap"]]
    return rows[:PAGE_SIZE], len(rows) > PAGE_SIZE


async def load_document(document_id: str) -> dict | None:
    """Một văn bản: thông tin, nhãn, văn bản liên quan, các Điều/mục kèm vị trí khoản/điểm để đặt neo link."""
    params = {"id": document_id, "as_of": date.today()}
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        document = await (await conn.execute(
            f"select {DOCUMENT_COLUMNS} from documents d left join quarantined_documents qd on qd.document_id = d.id "
            "where d.id = %(id)s", params)).fetchone()
        if document is None:
            return None
        document["nhan"] = labels(document)
        document["lien_quan"] = await (await conn.execute("""
            select case when r.from_doc = %(id)s then 'den' else 'tu' end as huong, r.relation_type,
                   o.id::text as id, o.so_hieu, o.tieu_de, o.ngay_ban_hanh, r.effective_from, r.source_label
            from document_relations r
            join documents o on o.id = case when r.from_doc = %(id)s then r.to_doc else r.from_doc end
            where (r.from_doc = %(id)s or r.to_doc = %(id)s) and r.relation_type in ('hop_nhat', 'sua_doi', 'thay_the', 'bai_bo')
            order by o.ngay_ban_hanh desc nulls last""", params)).fetchall()
        sections = await (await conn.execute("""
            select ch.id as chunk_id, ch.text, p.level, p.so, p.ten
            from chunks ch join provisions p on p.id = ch.dieu_provision_id
            where ch.document_id = %(id)s order by p.ordinal""", params)).fetchall()
        positions = await (await conn.execute("""
            select cp.chunk_id, cp.char_start, cp.level, cp.so from chunk_positions cp
            join chunks ch on ch.id = cp.chunk_id
            where ch.document_id = %(id)s and cp.level in ('khoan', 'diem')""", params)).fetchall()
    starts = {(p["chunk_id"], p["char_start"]): p for p in positions}
    document["phan"] = []
    if document["text_origin"] == "native":  # chữ OCR không hiện như chữ thật (quy tắc bất biến số 2)
        for section in sections:
            lines, offset = [], 0
            for text in section["text"].split("\n"):
                part = starts.get((section["chunk_id"], offset))
                lines.append({"text": text, "cap": part["level"] if part else None,
                              "neo": f"k-{section['chunk_id']}-{offset}" if part else None})
                offset += len(text) + 1
            document["phan"].append({"neo": f"d-{section['chunk_id']}", "nhan": provision_label(section["level"], section["so"]),
                                     "ten": section["ten"], "dong": lines})
    document["co_ban_goc"] = original_file(document) is not None
    return document


def original_file(document: dict) -> Path | None:
    """File đính kèm gốc (PDF/Word) của văn bản nếu đã tải về; văn bản chỉ có HTML thì không có."""
    raw_path = config.PROJECT_ROOT / document["raw_path"]
    if not raw_path.is_file():
        return None
    attachment = read_attachments.find_attachment(json.loads(raw_path.read_bytes())["data"])
    return attachment.source if attachment else None


async def load_thread_turns(thread_id: str, user_id: int) -> list[dict]:
    """Các lượt hỏi–đáp đã lưu của một cuộc hội thoại của người này (bản ghi chính thức: questions/answers, không
    phải checkpoint), kèm đánh giá đã chấm."""
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        return await (await conn.execute("""
            select q.text as cau_hoi, q.kind, q.as_of_date, a.id as answer_id, a.text as tra_loi, a.ket_luan,
                   a.has_cause, a.citations, f.verdict, f.note
            from conversations c join questions q on q.thread_id = c.thread_id
                                 join answers a on a.question_id = q.id
                                 left join answer_feedback f on f.answer_id = a.id
            where c.thread_id = %s and c.user_id = %s and c.hidden_at is null
            order by q.asked_at""", (thread_id, user_id))).fetchall()


THREAD_LIST_LIMIT = 30


async def list_threads(user_id: int) -> list[dict]:
    """Các cuộc hội thoại gần nhất của người này cho thanh bên: câu hỏi đầu tiên làm tên."""
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        return await (await conn.execute(f"""
            select c.thread_id, (array_agg(q.text order by q.asked_at))[1] as ten, max(q.asked_at) as luc
            from conversations c join questions q on q.thread_id = c.thread_id
            where c.user_id = %s and c.hidden_at is null
            group by c.thread_id order by max(q.asked_at) desc limit {THREAD_LIST_LIMIT}""", (user_id,))).fetchall()

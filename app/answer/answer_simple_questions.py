"""Hai nhánh cho câu hỏi đơn giản (docs/architecture.md, Model AI — rẽ nhánh theo loại câu hỏi):

- chào hỏi / không phải câu hỏi → câu trả lời mẫu, không tìm, không gọi model;
- khái niệm ("thuế là gì") → tra thẳng khoản "<thuật ngữ> là …" trong Điều "Giải thích từ ngữ" hoặc Điều mang
  đúng tên khái niệm, của văn bản dùng
  được tại mốc hỏi; kết luận chính là câu định nghĩa, rồi đi tiếp kiểm trích dẫn như mọi câu trả lời.
  Không thấy → luồng tìm thường (answer_graph).
Cả hai không gọi model nên trả lời gần như tức thì.
"""

import re

import psycopg
from psycopg.rows import dict_row

from app import config
from app.answer.search_articles import AUTHORITY_WEIGHT_SQL, NEEDS_VALIDITY_CHECK_SQL, REPLACED_BY_SQL

SMALL_TALK_ANSWER = (
    "Chào bạn! Mình là trợ lý tra cứu pháp luật thuế. Bạn hãy hỏi một câu về thuế, ví dụ "
    "\"Nộp hồ sơ khai thuế chậm 61 ngày bị phạt bao nhiêu?\" hoặc \"Thuế là gì?\". "
    "Mỗi câu trả lời đều trích nguyên văn Điều luật và ghi mốc thời gian áp dụng."
)

# Khoản/điểm mở đầu bằng "<thuật ngữ> là" trong Điều tên "Giải thích từ ngữ"; cùng bộ lọc dùng được như tìm kiếm.
DEFINITION_SQL = f"""
    select ch.id as chunk_id, d.id::text as document_id, d.so_hieu, d.tieu_de, d.loai, d.text_origin, d.source_url,
           a.level as dieu_level, a.so as dieu_so, a.ten as dieu_ten, k.text as dinh_nghia,
           {NEEDS_VALIDITY_CHECK_SQL} as can_kiem_hieu_luc, {REPLACED_BY_SQL} as het_hieu_luc,
           null::text as ly_do_cach_ly, 1.0 as score
    from provisions k
    join provisions a on a.id = k.parent_id and a.level = 'dieu'
    join chunks ch on ch.dieu_provision_id = a.id
    join documents d on d.id = k.document_id
    where k.level in ('khoan', 'diem')
      -- Điều "Giải thích từ ngữ", hoặc Điều mang đúng tên khái niệm: Luật Quản lý thuế 108/2025 đặt
      -- "Điều … Hóa đơn điện tử", khoản 1 "Hóa đơn điện tử là …" (gặp 23/10/2026)
      and (lower(f_unaccent(a.ten)) like 'giai thich tu ngu%%' or lower(f_unaccent(a.ten)) = %(term)s)
      and lower(f_unaccent(k.text)) ~ %(pattern)s
      and d.text_origin = 'native'
      and not exists (select 1 from quarantined_documents qd where qd.document_id = d.id)
      and d.content_matches_number is not false
      and (d.eff_from is null or d.eff_from <= %(as_of)s)
      and (d.eff_to is null or d.eff_to > %(as_of)s)
      and not (coalesce(d.eff_status_code, '') = 'HHL' and d.eff_to is null)
      and (d.doc_group <> 'VBHN' or d.ngay_ban_hanh is null or d.ngay_ban_hanh <= %(as_of)s)
    -- tên cột tự đặt không dùng được trong biểu thức ORDER BY → lặp lại biểu thức
    order by {REPLACED_BY_SQL} is not null, can_kiem_hieu_luc, {AUTHORITY_WEIGHT_SQL} desc, d.ngay_ban_hanh desc nulls last
    limit 1"""
NUMBER_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]|[a-zđ][)/.])\s*")


async def reply_small_talk(state: dict) -> dict:
    """Node LangGraph: câu trả lời mẫu cho câu chào / không phải câu hỏi."""
    return {"articles": [], "draft": {"co_can_cu": False, "ket_luan": SMALL_TALK_ANSWER, "can_cu": []},
            "citations": [], "unverified_numbers": [], "has_cause": False, "claim_support": [],
            "support_score": None, "answer_text": SMALL_TALK_ANSWER, "write_usage": []}


async def look_up_definition(state: dict) -> dict:
    """Node LangGraph: định nghĩa trong luật. Không thấy → articles rỗng, answer_graph chuyển sang tìm thường."""
    term = state.get("concept_term") or ""
    # Đã bỏ dấu và chỉ còn [a-z0-9 ] (detect_simple_question) — an toàn để ghép vào biểu thức chính quy.
    pattern = rf"^\s*(\d+(\.\d+)*[.)]|[a-z][)/.])?\s*{re.escape(term)}\s+(la|duoc hieu la)\s"
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        row = await (await conn.execute(DEFINITION_SQL, {"pattern": pattern, "term": term, "as_of": state["as_of_date"]})).fetchone()
    if row is None:
        return {"articles": []}
    definition = row.pop("dinh_nghia")
    sentence = NUMBER_PREFIX.sub("", definition, count=1)
    return {
        "articles": [row],
        "draft": {"co_can_cu": True, "ket_luan": sentence, "can_cu": [{"doan": 1, "trich_dan": definition}]},
        "write_usage": [],
    }

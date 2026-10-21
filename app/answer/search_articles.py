"""Tìm Điều luật bằng full-text — bản demo. Bước Tìm kiếm sẽ thay bằng tìm kết hợp + embedding + reranker.

Không lọc cứng "còn hiệu lực": 90/107 văn bản hợp nhất để trống trạng thái, luật gốc đang dùng thường là HHL1P
(docs/nguon-du-lieu.md). Lọc theo ngày hiệu lực tại mốc, và bỏ văn bản HHL không rõ ngày hết hiệu lực.
"""

import re

import psycopg
from psycopg.rows import dict_row

from app import config
from app.answer.understand_question import remove_diacritics

RESULT_LIMIT = 4
# Từ chức năng (đã bỏ dấu) — không giúp tìm, chỉ làm truy vấn OR nhiễu.
STOP_WORDS = set(
    "la bao nhieu thi the nao cua va co duoc cho cac nhung mot toi can hoi ve ra sao gi khong voi nay do khi neu bi "
    "phai theo hay hoac thuoc tai trong tren duoi nhu vay con nua a oi a nhe a".split()
)
# Xếp văn bản luật trước văn bản hướng dẫn, công văn sau cùng (docs/architecture.md, Model AI).
AUTHORITY_WEIGHT_SQL = """
    case when d.doc_group = 'VBHN' then 1.4
         when d.loai in ('Luật', 'Bộ luật', 'Nghị quyết') then 1.4
         when d.loai = 'Nghị định' then 1.2
         when d.loai = 'Công văn' then 0.7
         else 1.0 end"""
# Điểm = khớp nội dung (chia 1 + log độ dài — cờ 1 của ts_rank_cd, tài liệu Postgres 18 mục 12.3.3; không thì Điều
# dài nhiều từ trùng luôn thắng) + khớp tên Điều × 2 (tên Điều là tín hiệu mạnh: "Điều 10. Thuế suất"), × thứ bậc.
# Đã thử khớp tên Điều theo từng từ (OR) — tệ hơn: tên Điều không liên quan có chữ "thuế suất" bị đẩy lên (22/10/2026).
SEARCH_SQL = f"""
    select ch.id as chunk_id, d.so_hieu, d.loai, d.text_origin, d.source_url, p.so as dieu_so, p.ten as dieu_ten,
           (ts_rank_cd(ch.fts, q.query, 1)
            + 2.0 * ts_rank_cd(to_tsvector('simple', f_unaccent(coalesce(p.ten, ''))), q.query))
           * {AUTHORITY_WEIGHT_SQL} as score
    from chunks ch
    join documents d on d.id = ch.document_id
    join provisions p on p.id = ch.dieu_provision_id
    cross join (select to_tsquery('simple', %(tsquery)s) as query) q
    where ch.fts @@ q.query
      and (d.eff_from is null or d.eff_from <= %(as_of)s)
      and (d.eff_to is null or d.eff_to > %(as_of)s)
      and not (d.eff_status_code = 'HHL' and d.eff_to is null)
      -- JSON chứa văn bản khác (vd NĐ 125/2020 chứa công văn đính chính): trích sẽ ghi sai số hiệu
      and d.content_matches_number is not false
      -- bản hợp nhất ban hành sau mốc hỏi đã gộp cả sửa đổi đến sau → không dùng cho mốc này
      and (d.doc_group <> 'VBHN' or d.ngay_ban_hanh is null or d.ngay_ban_hanh <= %(as_of)s)
      -- ưu tiên văn bản hợp nhất: đã có bản hợp nhất có chữ tại mốc hỏi thì ẩn văn bản gốc ...
      and not exists (
          select 1 from document_relations r join documents v on v.id = r.from_doc
          where r.relation_type = 'hop_nhat' and r.to_doc = d.id
            and (v.ngay_ban_hanh is null or v.ngay_ban_hanh <= %(as_of)s)
            and exists (select 1 from chunks vc where vc.document_id = v.id))
      -- ... và ẩn bản hợp nhất cũ khi đã có bản hợp nhất mới hơn (cùng văn bản gốc) tại mốc hỏi
      and not exists (
          select 1 from document_relations mine
          join document_relations newer on newer.to_doc = mine.to_doc and newer.relation_type = 'hop_nhat'
          join documents v on v.id = newer.from_doc
          where mine.from_doc = d.id and mine.relation_type = 'hop_nhat' and newer.from_doc <> d.id
            and v.ngay_ban_hanh > d.ngay_ban_hanh and v.ngay_ban_hanh <= %(as_of)s
            and exists (select 1 from chunks vc where vc.document_id = v.id))
    order by score desc
    limit %(limit)s"""


def build_tsqueries(text: str) -> list[str]:
    """Hai truy vấn: mọi từ phải có (AND), rồi nới ra chỉ cần một từ (OR). Bỏ dấu giống cột fts (f_unaccent)."""
    words = [w for w in re.findall(r"[a-z0-9]+", remove_diacritics(text)) if w not in STOP_WORDS]
    words = list(dict.fromkeys(words))
    if not words:
        return []
    return [" & ".join(words), " | ".join(words)]


async def search_articles(state: dict) -> dict:
    """Node LangGraph. Chỉ giữ id và thông tin văn bản trong state — không nhét chữ luật vào state."""
    results = []
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        for tsquery in build_tsqueries(state["search_text"]):
            cursor = await conn.execute(
                SEARCH_SQL, {"tsquery": tsquery, "as_of": state["as_of_date"], "limit": RESULT_LIMIT}
            )
            results = await cursor.fetchall()
            if len(results) >= RESULT_LIMIT:
                break
    for row in results:
        row["score"] = round(float(row["score"]), 4)
    return {"articles": results}


async def load_chunk_texts(chunk_ids: list[int]) -> dict[int, str]:
    """Chữ của các Điều theo id — đọc lại từ database thay vì giữ trong state."""
    if not chunk_ids:
        return {}
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        cursor = await conn.execute("select id, text from chunks where id = any(%s)", (chunk_ids,))
        return dict(await cursor.fetchall())

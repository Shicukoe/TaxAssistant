"""Tìm Điều luật: kết hợp từ khoá (full-text) + theo nghĩa (BGE-M3, pgvector), gộp bằng reciprocal rank fusion
(docs/architecture.md, Tìm kiếm). Chưa có reranker.

Không lọc cứng "còn hiệu lực": 90/107 văn bản hợp nhất để trống trạng thái, luật gốc đang dùng thường là HHL1P
(docs/nguon-du-lieu.md). Lọc theo ngày hiệu lực tại mốc, và bỏ văn bản HHL không rõ ngày hết hiệu lực.
"""

import re
from datetime import date

import httpx
import psycopg
from psycopg.rows import dict_row

from app import config
from app.answer.call_local_model import embed_texts
from app.answer.understand_question import remove_diacritics

RESULT_LIMIT = 4
# Câu hỏi nhiều ý (split_question): mỗi ý lấy tối đa PER_PART Điều, lần lượt từng ý, tổng tối đa MAX_SPLIT_RESULTS
PER_PART = 2
MAX_SPLIT_RESULTS = 8
LEVEL_NAMES = {"diem": "điểm", "khoan": "khoản", "dieu": "Điều", "muc": "mục", "doan": "đoạn"}
PART_AND_SECTION = re.compile(r"([A-ZĐ])\.([IVXL]+)")  # 'B.II' = mục II phần B (split_articles)
# Từ chức năng (đã bỏ dấu) — không giúp tìm, chỉ làm truy vấn OR nhiễu.
STOP_WORDS = set(
    "la bao nhieu thi the nao cua va co duoc cho cac nhung mot toi can hoi ve ra sao gi khong voi nay do khi neu bi "
    "phai theo hay hoac thuoc tai trong tren duoi nhu vay con nua a oi a nhe a".split()
)
# Cụm chỉ thời gian (đã bỏ dấu): "ngày 5/3/2025", "tháng 7 năm 2026", "năm 2026", "2026", "hiện nay", "hiện hành".
TIME_EXPRESSION = re.compile(
    r"\b(?:ngay\s+)?\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b(?:ngay|thang|nam|quy|ky)\s+\d{1,4}\b|\b(?:19|20)\d{2}\b"
    r"|\bhien (?:nay|hanh|tai)\b"
)
# Xếp văn bản luật trước văn bản hướng dẫn, công văn sau cùng (docs/architecture.md, Model AI).
AUTHORITY_WEIGHT_SQL = """
    case when d.doc_group = 'VBHN' then 1.4
         when d.loai in ('Luật', 'Bộ luật', 'Nghị quyết') then 1.4
         when d.loai = 'Nghị định' then 1.2
         when d.loai = 'Công văn' then 0.7
         else 1.0 end"""
# Chữ OCR (PDF) không được trích, chỉ hiện số hiệu + link. Đoạn PDF dài, ngắt dòng giữa câu, khớp truy vấn OR rất
# nhiều lần nên điểm từ khoá cao bất thường → hạ trọng số để không lấn các đoạn chữ gốc.
OCR_WEIGHT_SQL = "case when d.text_origin = 'ocr' then 0.3 else 1.0 end"
# "Cần kiểm hiệu lực" (docs/architecture.md, Dữ liệu): cổng ghi còn hiệu lực, không có ngày hết hiệu lực, ban hành
# trước mốc hỏi hơn 10 năm — hiệu lực ghi trên cổng không đáng tin ở văn bản cũ (NĐ 24/2007 về TNDN vẫn ghi "còn").
# Văn bản hợp nhất không áp (mang ngày ban hành mới). Văn bản mang nhãn xếp SAU mọi văn bản không mang nhãn — chỉ
# hạ trọng số thì văn bản cũ nhiều từ trùng vẫn đứng trước luật hiện hành.
NEEDS_VALIDITY_CHECK_SQL = """(d.doc_group <> 'VBHN' and d.eff_to is null
         and coalesce(d.eff_status_code, '') in ('CHL', 'HHL1P', '')
         and d.ngay_ban_hanh < %(as_of)s::date - interval '10 years')"""
# Văn bản bị văn bản mới tuyên bố hết hiệu lực tại mốc hỏi (view document_replacements, migration 009): vẫn tìm được
# — còn ngoại lệ "trừ …", quy định chuyển tiếp — nhưng xếp sau mọi văn bản khác và luôn mang nhãn ghi rõ văn bản nào
# tuyên bố, ở khoản nào. NULL = không bị thay tại mốc hỏi.
REPLACED_BY_SQL = """(
    select jsonb_build_object('tu_ngay', x.effective_from, 'theo_loai', n.loai, 'theo_so_hieu', n.so_hieu,
                              'vi_tri', x.source_label, 'con_ngoai_le', x.has_exceptions,
                              'van_ban_bi_thay', case when o.id <> d.id then o.so_hieu end)
    from document_replacements x
    join documents n on n.id = x.replaced_by
    join documents o on o.id = x.replaced_document
    where x.document_id = d.id and x.effective_from <= %(as_of)s
    order by x.effective_from desc limit 1)"""
# Cột chung của hai đường tìm. uu_tien = thứ bậc × hệ số OCR, nhân vào điểm sau khi gộp (RRF chỉ dùng thứ hạng).
SELECT_COLUMNS = f"""
    ch.id as chunk_id, d.id::text as document_id, d.so_hieu, d.tieu_de, d.loai, d.text_origin, d.source_url,
    p.level as dieu_level, p.so as dieu_so, p.ten as dieu_ten,
    {NEEDS_VALIDITY_CHECK_SQL} as can_kiem_hieu_luc,
    {REPLACED_BY_SQL} as het_hieu_luc,
    qd.reasons as ly_do_cach_ly,
    ({AUTHORITY_WEIGHT_SQL}) * ({OCR_WEIGHT_SQL}) as uu_tien"""
FROM_SQL = """
    from chunks ch
    join documents d on d.id = ch.document_id
    join provisions p on p.id = ch.dieu_provision_id
    -- văn bản bị cách ly (docs/architecture.md, lớp 2) vẫn tìm được, nhưng check_citations không trích
    left join quarantined_documents qd on qd.document_id = d.id"""
# Bộ lọc chung: dùng được tại mốc hỏi. Giống nhau cho từ khoá và theo nghĩa — hai đường không được lệch nhau.
FILTER_SQL = """
          (d.eff_from is null or d.eff_from <= %(as_of)s)
      and (d.eff_to is null or d.eff_to > %(as_of)s)
      -- coalesce: trạng thái trống (NULL) làm cả điều kiện thành NULL → dòng bị loại; phần lớn văn bản hợp nhất
      -- không ghi trạng thái.
      and not (coalesce(d.eff_status_code, '') = 'HHL' and d.eff_to is null)
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
            and exists (select 1 from chunks vc where vc.document_id = v.id))"""
# Từ khoá: khớp nội dung (chia 1 + log độ dài — cờ 1 của ts_rank_cd, tài liệu Postgres 18 mục 12.3.3; không thì Điều
# dài nhiều từ trùng luôn thắng) + khớp tên Điều × 2 (tên Điều là tín hiệu mạnh: "Điều 10. Thuế suất").
# Tên Điều khớp theo cả truy vấn, không theo từng từ (OR): khớp từng từ đẩy tên Điều không liên quan lên.
KEYWORD_MATCH_SQL = f"""
    select {SELECT_COLUMNS},
           ts_rank_cd(ch.fts, q.query, 1)
           + 2.0 * ts_rank_cd(to_tsvector('simple', f_unaccent(coalesce(p.ten, ''))), q.query) as diem
    {FROM_SQL}
    cross join (select to_tsquery('simple', %(tsquery)s) as query) q
    where ch.fts @@ q.query and {FILTER_SQL}"""
# Postgres không cho dùng tên cột tự đặt (diem, uu_tien) trong biểu thức ORDER BY → bọc thêm một lớp select.
KEYWORD_SQL = f"""
    select * from ({KEYWORD_MATCH_SQL}) matched
    order by diem * uu_tien desc
    limit %(limit)s"""
# Theo nghĩa: khoảng cách cosine của pgvector (<=>), tìm chính xác — không chỉ mục; ~17.000 đoạn vẫn nhanh và không
# sót kết quả khi có bộ lọc (chỉ mục xấp xỉ lấy ứng viên trước rồi mới lọc → có thể thiếu).
VECTOR_SQL = f"""
    select {SELECT_COLUMNS}, 1 - (e.vec <=> %(vector)s::vector) as diem
    {FROM_SQL}
    join embeddings e on e.chunk_id = ch.id and e.model_name = %(model)s and e.model_version = %(version)s
    where {FILTER_SQL}
    order by e.vec <=> %(vector)s::vector
    limit %(limit)s"""
CANDIDATES = 20  # số ứng viên mỗi đường tìm (từ khoá, theo nghĩa) trước khi gộp
RRF_K = 60  # reciprocal rank fusion: điểm = tổng 1 / (60 + thứ hạng) — Cormack, Clarke, Büttcher, SIGIR 2009


def provision_label(level: str, number: str) -> str:
    """'Điều 13', 'mục II phần B', 'đoạn 2' — cách gọi một phần văn bản khi trích dẫn."""
    if level == "muc" and (m := PART_AND_SECTION.fullmatch(number)):
        return f"mục {m[2]} phần {m[1]}"
    return f"{LEVEL_NAMES[level]} {number}"


def build_tsqueries(text: str) -> list[str]:
    """Hai truy vấn: mọi từ phải có (AND), rồi nới ra chỉ cần một từ (OR). Bỏ dấu giống cột fts (f_unaccent).

    Cụm chỉ thời gian bị bỏ: mốc thời gian đã lấy riêng (understand_question) và lọc ở SQL theo hiệu lực. Để lại thì
    AND đòi Điều luật chứa chữ "năm 2026" — Điều đúng thường không chứa nên bị loại.
    """
    plain = TIME_EXPRESSION.sub(" ", remove_diacritics(text))
    words = [w for w in re.findall(r"[a-z0-9]+", plain) if w not in STOP_WORDS]
    words = list(dict.fromkeys(words))
    if not words:
        return []
    return [" & ".join(words), " | ".join(words)]


async def keyword_candidates(conn, search_text: str, as_of) -> list[dict]:
    """AND trước; ít hơn CANDIDATES thì thêm kết quả OR (bỏ trùng)."""
    rows: list[dict] = []
    for tsquery in build_tsqueries(search_text):
        seen = {row["chunk_id"] for row in rows}
        cursor = await conn.execute(KEYWORD_SQL, {"tsquery": tsquery, "as_of": as_of, "limit": CANDIDATES})
        rows += [row for row in await cursor.fetchall() if row["chunk_id"] not in seen]
        if len(rows) >= CANDIDATES:
            break
    return rows[:CANDIDATES]


async def vector_candidates(conn, search_text: str, as_of) -> list[dict]:
    [vector] = await embed_texts([search_text])
    cursor = await conn.execute(VECTOR_SQL, {"vector": str(vector), "as_of": as_of, "limit": CANDIDATES,
                                             "model": config.EMBEDDING_MODEL, "version": config.EMBEDDING_MODEL_VERSION})
    return await cursor.fetchall()


def fuse(ranked_lists: dict[str, list[dict]]) -> list[dict]:
    """Gộp các danh sách bằng RRF × uu_tien. Văn bản đã bị thay xếp cuối, rồi tới văn bản "cần kiểm hiệu lực"."""
    merged: dict[int, dict] = {}
    for source, rows in ranked_lists.items():
        for rank, row in enumerate(rows, start=1):
            item = merged.setdefault(row["chunk_id"], {**row, "score": 0.0, "nguon": []})
            item["score"] += 1 / (RRF_K + rank)
            item["nguon"].append(f"{source} #{rank}")
    for item in merged.values():
        item["score"] = round(item["score"] * float(item.pop("uu_tien")), 5)
        item.pop("diem", None)
    return sorted(merged.values(),
                  key=lambda item: (item["het_hieu_luc"] is not None, item["can_kiem_hieu_luc"], -item["score"]))


def expiry_note(replaced: dict) -> str:
    """Nhãn cho người đọc: 'Đã hết hiệu lực từ 01/07/2026 theo khoản 3 Điều 52 Luật 108/2025/QH15 …'."""
    day = replaced["tu_ngay"]
    day = date.fromisoformat(day) if isinstance(day, str) else day
    whose = "" if replaced["van_ban_bi_thay"] is None else f" (bản hợp nhất của {replaced['van_ban_bi_thay']})"
    note = (f"Đã hết hiệu lực từ {day:%d/%m/%Y}{whose} theo {replaced['vi_tri']} {replaced['theo_loai']} "
            f"{replaced['theo_so_hieu']} — cổng dữ liệu chưa ghi ngày hết hiệu lực")
    return note + ("; một số quy định còn áp dụng theo ngoại lệ ghi tại đó" if replaced["con_ngoai_le"] else "")


async def search(search_text: str, as_of, mode: str = "ket_hop") -> tuple[list[dict], str | None]:
    """mode: 'tu_khoa' | 'nghia' | 'ket_hop'. Trả (kết quả, lỗi tìm theo nghĩa nếu có — để hiện ở debug)."""
    lists, vector_error = {}, None
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        if mode in ("tu_khoa", "ket_hop"):
            lists["tu_khoa"] = await keyword_candidates(conn, search_text, as_of)
        if mode in ("nghia", "ket_hop"):
            try:
                lists["nghia"] = await vector_candidates(conn, search_text, as_of)
            except httpx.HTTPError as e:  # server embedding tắt → vẫn trả lời bằng từ khoá
                vector_error = f"{type(e).__name__}: server embedding chưa chạy (bash scripts/run_embedding_server.sh)"
    return fuse(lists), vector_error


def interleave(result_lists: list[list[dict]]) -> list[dict]:
    """Lần lượt từng ý lấy Điều kế tiếp CHƯA có trong danh sách, mỗi ý tối đa PER_PART Điều — ý trùng kết quả với ý
    trước vẫn góp Điều của riêng nó ("điều kiện hóa đơn" và "chi phí được trừ" cùng ra Điều 9, 10 trước tiên)."""
    picked, seen = [], set()
    unseen = [iter(results) for results in result_lists]
    for _ in range(PER_PART):
        for part, results in enumerate(unseen, start=1):
            article = next((a for a in results if a["chunk_id"] not in seen), None)
            if article is not None and len(picked) < MAX_SPLIT_RESULTS:
                seen.add(article["chunk_id"])
                picked.append({**article, "nguon": [f"y{part}"] + article["nguon"]})
    return picked


async def search_articles(state: dict) -> dict:
    """Node LangGraph: tìm kết hợp — mỗi ý của câu hỏi một lần (split_question). Chỉ giữ id và thông tin văn bản
    trong state — không nhét chữ luật vào state."""
    parts = state.get("search_parts") or [state["search_text"]]
    found = [await search(part, state["as_of_date"]) for part in parts]
    vector_error = next((error for _, error in found if error), None)
    if len(parts) == 1:
        return {"articles": found[0][0][:RESULT_LIMIT], "search_warning": vector_error}
    return {"articles": interleave([results for results, _ in found]), "search_warning": vector_error}


async def load_chunk_texts(chunk_ids: list[int]) -> dict[int, str]:
    """Chữ của các Điều theo id — đọc lại từ database thay vì giữ trong state."""
    if not chunk_ids:
        return {}
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        cursor = await conn.execute("select id, text from chunks where id = any(%s)", (chunk_ids,))
        return dict(await cursor.fetchall())

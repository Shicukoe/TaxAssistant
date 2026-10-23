"""Nối văn bản hợp nhất với văn bản gốc, và kiểm JSON có đúng là văn bản đó không.

Chạy (sau save_to_database; trong pipeline: công đoạn consolidated_links):
    python -m app.ingest.link_consolidated_documents
    python -m app.ingest.link_consolidated_documents --check     (bài tự kiểm, không cần database)

1. Đoạn mở đầu của văn bản hợp nhất có khuôn cố định (Pháp lệnh Hợp nhất):
     "Nghị định số 125/2020/NĐ-CP ngày … có hiệu lực kể từ ngày …, được sửa đổi, bổ sung bởi:
      Nghị định số 102/2021/NĐ-CP …; Nghị định số 310/2025/NĐ-CP …"
   → document_relations: hop_nhat (bản hợp nhất → văn bản gốc), sua_doi (văn bản sửa → văn bản gốc).
   Văn bản hợp nhất chưa có chữ (JSON rỗng) thì chỉ đọc được tiêu đề.
2. Số hiệu ghi ở đầu chữ ("Số: 29 /CP-KTTH") phải khớp số hiệu của văn bản → documents.content_matches_number.

Tính lại toàn bộ mỗi lần chạy (107 văn bản hợp nhất, vài giây) — không có trạng thái để lệch.
"""

import json
import logging
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg

from app import config
from app.ingest import download_moj_documents as moj
from app.ingest import read_attachments
from app.ingest.split_articles import html_to_text_lines
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

PREAMBLE_CHARS = 6000  # đoạn mở đầu nằm trước Điều 1; văn bản hợp nhất dài nên chỉ đọc phần đầu
HEADER_CHARS = 1200  # dòng "Số: …" nằm ở phần quốc hiệu
AMENDED_BY = re.compile(r"được\s+sửa\s+đổi,?\s+bổ\s+sung\s+bởi", re.IGNORECASE)
# "số 125/2020/NĐ-CP ngày 19 tháng 10 năm 2020" — ngày để phân biệt số hiệu trùng nhau
REFERENCE = re.compile(
    r"\bsố\s+(\d[\w./\-]*)(?:\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4}))?", re.IGNORECASE
)
# Dòng "Số: 29 /CP-KTTH" ở phần quốc hiệu. Chỉ nhận "Số:" có dấu hai chấm hoặc "SỐ" viết hoa — chữ "số" thường
# nằm trong câu "Căn cứ Nghị định số …" (đo 22/10: bắt nhầm hàng trăm văn bản). Chỉ lấy CON SỐ ĐẦU: số hiệu viết
# khác dạng giữa đầu văn bản và cổng ("44 - TC/CTN", "39-TC/TCT" so với "39/1997/TT-BTC") là chuyện thường.
# Phân biệt hoa thường: câu dẫn chiếu viết "quyết định số: 54", "Nghị định số: 89" (đo 22/10, 4 ca báo nhầm).
HEADER_NUMBER = re.compile(r"\bSố\s*:\s*(\d+)")
# Văn bản cũ không có dòng "Số:" mà viết "QUYẾT ĐỊNH CỦA BỘ TRƯỞNG BỘ TÀI CHÍNH SỐ 1352/1998/…" — chỉ nhận
# "SỐ" ngay sau loại văn bản ĐẦU TIÊN của tiêu đề; tiêu đề hay nhắc văn bản khác ("… QUY ĐỊNH TẠI NGHỊ ĐỊNH SỐ 19/2015").
FIRST_DOC_TYPE = re.compile(r"\b(?:THÔNG TƯ|QUYẾT ĐỊNH|CÔNG VĂN|NGHỊ ĐỊNH|NGHỊ QUYẾT|CHỈ THỊ|LUẬT|PHÁP LỆNH)\b")
LEADING_NUMBER = re.compile(r"\s*(\d+)")


def normalize_number(number: str) -> str:
    """'73A-TC/TCT', '73/A-TC-TCT', 'SỐ 73A TC/TCT' → '73ATCTCT'. 'Ð' (chữ Eth hay gặp trong dữ liệu cũ) → 'Đ'."""
    return re.sub(r"[^0-9A-ZĐ]", "", number.upper().replace("Ð", "Đ"))


def plain_text(doc: dict, limit: int) -> str:
    if not moj.has_text_content(doc):
        return ""
    text = " ".join(line.text for line in html_to_text_lines(doc["documentContent"]["content"]))
    return text[:limit]


def attachment_text(doc: dict, limit: int) -> str:
    """Chữ đầu file đính kèm — cho văn bản hợp nhất có JSON rỗng. Chỉ để đọc số hiệu, không trích."""
    attachment = read_attachments.find_attachment(doc)
    if attachment is None:
        return ""
    return " ".join(line.text for line in read_attachments.read_attachment_lines(attachment))[:limit]


def find_references(text: str) -> list[tuple[str, date | None]]:
    """Các (số hiệu, ngày ban hành) theo thứ tự xuất hiện sau chữ "số"."""
    references = []
    for match in REFERENCE.finditer(text):
        number = match.group(1).rstrip(".,;")
        issued = None
        if match.group(4):
            try:
                issued = date(int(match.group(4)), int(match.group(3)), int(match.group(2)))
            except ValueError:
                pass
        references.append((number, issued))
    return references


def read_consolidation_sources(own_number: str, title: str, preamble: str) -> tuple[list, list, str]:
    """(văn bản gốc, văn bản sửa đổi, nguồn đọc). Ưu tiên đoạn mở đầu; không có chữ thì đọc tiêu đề."""
    own = normalize_number(own_number)
    if preamble:
        split_at = AMENDED_BY.search(preamble)
        before = preamble[: split_at.start()] if split_at else preamble
        after = preamble[split_at.end():] if split_at else ""
        base = [r for r in find_references(before) if normalize_number(r[0]) != own]
        amending = [r for r in find_references(after) if normalize_number(r[0]) != own]
        if base:
            return base[:1], amending, "vbhn_preamble"
    title_refs = [r for r in find_references(title) if normalize_number(r[0]) != own]
    return title_refs[:1], [], "vbhn_title"


def read_header_number(text: str) -> str | None:
    header = text[:HEADER_CHARS]
    match = HEADER_NUMBER.search(header)
    if match:
        return match.group(1)
    doc_type = FIRST_DOC_TYPE.search(header)
    if doc_type:
        after_type = header[doc_type.end():]
        match = re.match(r"(?:\s+LIÊN TỊCH)?(?:\s+CỦA\s+\D{0,60}?)?\s+SỐ\s*:?\s*(\d+)", after_type)
        if match:
            return match.group(1)
    return None


def header_matches_number(header: str, so_hieu: str) -> bool | None:
    """So con số đầu: '29' với '125/2020/NĐ-CP' → False. Số hiệu không bắt đầu bằng số ('Không số') → None."""
    own = LEADING_NUMBER.match(so_hieu)
    return int(header) == int(own.group(1)) if own else None


def link_consolidated_documents() -> StageReport:
    report = StageReport("van_ban_hop_nhat")
    with psycopg.connect(config.DATABASE_CONNECTION, autocommit=True) as conn:
        documents = conn.execute(
            "select id, so_hieu, doc_group, ngay_ban_hanh, raw_path from documents where raw_path is not null"
        ).fetchall()
        by_number = defaultdict(list)  # số hiệu chuẩn hoá → [(id, ngày ban hành)] — số hiệu không phải khoá
        for document_id, so_hieu, doc_group, issued, _ in documents:
            if doc_group != "VBHN":
                by_number[normalize_number(so_hieu)].append((document_id, issued))

        def resolve(number: str, issued: date | None, label: str):
            candidates = by_number.get(normalize_number(number), [])
            if issued and len(candidates) > 1:
                candidates = [c for c in candidates if c[1] == issued] or candidates
            if len(candidates) == 1:
                return candidates[0][0]
            report.count("khong_tim_thay_van_ban" if not candidates else "so_hieu_trung_khong_phan_biet_duoc")
            if candidates:
                log.info("%s: %s trùng %d văn bản", label, number, len(candidates))
            return None

        relations, content_checks = [], []
        for document_id, so_hieu, doc_group, _, raw_path in documents:
            try:
                doc = json.loads(Path(raw_path).read_bytes())["data"]
                text = plain_text(doc, PREAMBLE_CHARS)
                header = read_header_number(text) if text else None
                matches = header_matches_number(header, so_hieu) if header else None
                content_checks.append((matches, document_id))
                report.count({True: "json_dung_van_ban", False: "json_lech_van_ban", None: "json_khong_kiem_duoc"}[matches])
                if matches is False:
                    report.fail(so_hieu, f"đầu văn bản ghi số '{header}'", log)
                if doc_group != "VBHN":
                    continue
                report.count("van_ban_hop_nhat")
                if not text and (text := attachment_text(doc, PREAMBLE_CHARS)):
                    report.count("doc_mo_dau_tu_file_dinh_kem")
                base, amending, evidence = read_consolidation_sources(so_hieu, doc.get("title") or "", text)
                base_id = resolve(*base[0], so_hieu) if base else None
                if base_id is None:
                    report.count("hop_nhat_chua_noi_duoc")
                    continue
                report.count(f"noi_tu_{evidence.removeprefix('vbhn_')}")
                # Ghi cả số hiệu gốc (to_doc_ref): nạp lại văn bản gốc làm to_doc thành NULL (ON DELETE SET NULL);
                # thiếu to_doc_ref thì vi phạm relation_has_target và văn bản gốc không nạp lại được.
                base_number = base[0][0]
                relations.append((document_id, base_id, base_number, "hop_nhat", evidence))
                for number, issued in amending:
                    amending_id = resolve(number, issued, so_hieu)
                    if amending_id and amending_id != base_id:
                        relations.append((amending_id, base_id, base_number, "sua_doi", evidence))
                        report.count("quan_he_sua_doi")
            except Exception as e:  # một văn bản lỗi không chặn văn bản khác (quy tắc bất biến số 11)
                report.fail(so_hieu, e, log)

        with conn.transaction():
            conn.execute("delete from document_relations where evidence in ('vbhn_preamble', 'vbhn_title')")
            conn.cursor().executemany(
                "insert into document_relations (from_doc, to_doc, to_doc_ref, relation_type, evidence, confidence) "
                "values (%s, %s, %s, %s, %s, 1.0)", relations
            )
            conn.cursor().executemany(
                "update documents set content_matches_number = %s where id = %s", content_checks
            )
    log.info(report.summary())
    return report


def self_check() -> None:
    preamble = ("VĂN BẢN HỢP NHẤT Số: 27/2026/VBHN-NĐ-BTC Hà Nội NGHỊ ĐỊNH Nghị định số 125/2020/NĐ-CP ngày 19 tháng 10 "
                "năm 2020 của Chính phủ quy định xử phạt, có hiệu lực kể từ ngày 05 tháng 12 năm 2020, được sửa đổi, "
                "bổ sung bởi: Nghị định số 102/2021/NĐ-CP ngày 16 tháng 11 năm 2021 của Chính phủ; Nghị định số "
                "310/2025/NĐ-CP ngày 02 tháng 12 năm 2025 sửa đổi Nghị định số 125/2020/NĐ-CP")
    base, amending, evidence = read_consolidation_sources("27/2026/VBHN-NĐ-BTC", "", preamble)
    assert evidence == "vbhn_preamble", evidence
    assert base == [("125/2020/NĐ-CP", date(2020, 10, 19))], base
    assert [n for n, _ in amending][:2] == ["102/2021/NĐ-CP", "310/2025/NĐ-CP"], amending
    base, _, evidence = read_consolidation_sources(
        "114/VBHN-VPQH", "Văn bản hợp nhất số 114/VBHN-VPQH 2026, hợp nhất Luật Thuế giá trị gia tăng số 48/2024/QH15", "")
    assert (base[0][0], evidence) == ("48/2024/QH15", "vbhn_title"), base
    assert normalize_number("73A-TC/TCT") == normalize_number("73/A-TC-TCT")
    assert normalize_number("1352/1998/QÐ/BTC") == normalize_number("1352/1998/QĐ/BTC")
    assert header_matches_number(read_header_number("CHÍNH PHỦ Số: 29 /CP-KTTH V/v đính chính"), "125/2020/NĐ-CP") is False
    assert header_matches_number(read_header_number("BỘ TÀI CHÍNH Số : 44 - TC/CTN Hà Nội"), "44 - TC/CTN") is True
    assert read_header_number("Căn cứ Luật Thuế giá trị gia tăng số 13/2008/QH12 ngày 03/6/2008") is None
    assert header_matches_number(read_header_number("QUYẾT ĐỊNH SỐ 1352/1998/QĐ/BTC"), "1352/1998/QÐ/BTC") is True
    assert header_matches_number("29", "Không số") is None
    assert read_header_number("QUỐC HỘI Nghị quyết số: 28/2016/QH14 NGHỊ QUYẾT SỬA ĐỔI NGHỊ QUYẾT SỐ 55/2014") is None
    assert read_header_number("ban hành theo quyết định số: 54 TC/TCT ngày 20-2-1991") is None
    assert read_header_number("THÔNG TƯ HƯỚNG DẪN CHÍNH SÁCH ... QUY ĐỊNH TẠI NGHỊ ĐỊNH SỐ 19/2015/NĐ") is None
    assert read_header_number("CÔNG VĂN CỦA BỘ TÀI CHÍNH SỐ 6209/BTC-TCT NGÀY 17") == "6209"
    print("PASS")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(link_consolidated_documents().summary())


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

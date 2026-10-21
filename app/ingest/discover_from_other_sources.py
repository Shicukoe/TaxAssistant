"""Phát hiện văn bản thuế mới từ nguồn KHÁC cổng Bộ Tư pháp, và tải bản gốc những văn bản Bộ Tư pháp chưa có.

Chạy (trong pipeline: công đoạn other_source_documents — không phụ thuộc nhánh Bộ Tư pháp):
    python -m app.ingest.discover_from_other_sources
    python -m app.ingest.discover_from_other_sources --check     (bài tự kiểm, không gọi mạng)

Nguồn (docs/pipeline-du-lieu.md, "Nhiều nguồn, tự chuyển khi hỏng"):
1. RSS "văn bản mới ban hành" của congbao — 50 văn bản mới nhất; trích yếu nằm ở <description>, mã văn bản ở cuối
   link (= id_van_ban của API tìm kiếm). API tìm kiếm trả danh sách file Word/PDF.
2. vanban.chinhphu.vn — docid tăng dần; dò từ docid lớn nhất đã biết. Trang không có "Số ký hiệu" = docid trống.
Nguồn nào chết (theo source_health) thì bỏ qua nguồn đó, nguồn còn lại vẫn chạy.
Chỉ LƯU bản gốc; nạp database khi đã có bước đọc file đính kèm. Ghi nguồn: congbao.chinhphu.vn, www.chinhphu.vn.
"""

import html
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from app import config
from app.ingest import download_moj_documents as moj
from app.ingest.check_sources import CONGBAO_NEW_DOCUMENTS_RSS, VANBAN_DOCUMENT_URL, is_source_alive
from app.ingest.download_from_congbao import search_congbao
from app.ingest.link_consolidated_documents import normalize_number
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

CONGBAO_NEW_DIR = config.RAW_DATA_DIR / "congbao" / "new"
CONGBAO_LAST_RUN_FILE = CONGBAO_NEW_DIR / "last_run.txt"
VANBAN_DIR = config.RAW_DATA_DIR / "vanban_chinhphu"
VANBAN_LAST_DOCID_FILE = VANBAN_DIR / "last_docid.txt"
VANBAN_HOME = "https://vanban.chinhphu.vn/"
VANBAN_MAX_DOCIDS_PER_RUN = 400  # 400 × 2 giây ≈ 13 phút
VANBAN_STOP_AFTER_EMPTY = 25  # docid có thể không liên tục — 25 docid trống liên tiếp mới coi là hết
TAX_WORDS = moj.TAX_WORDS_IN_TITLE
VANBAN_FIELDS = re.compile(
    r"Số ký hiệu\s+(?P<so_hieu>.*?)\s+Ngày ban hành\s+(?P<ngay>\S+)\s+Loại văn bản\s+(?P<loai>.*?)\s+"
    r"Cơ quan ban hành\s+(?P<co_quan>.*?)\s+Người ký\s+(?P<nguoi_ky>.*?)\s+Trích yếu\s+(?P<trich_yeu>.*?)"
    r"\s+(?:Tài liệu đính kèm|Các văn bản khác)"
)
VANBAN_FILE_LINK = re.compile(r"https?://datafiles\.chinhphu\.vn/cpp/files/vbpq/[^\"'\s<>]+")
DOCID_LINK = re.compile(r"docid=(\d+)")


def page_text(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def parse_vanban_page(page: str) -> dict | None:
    """Thông tin văn bản trên trang chi tiết; None nếu docid trống."""
    match = VANBAN_FIELDS.search(page_text(page))
    if not match:
        return None
    return {**match.groupdict(), "files": list(dict.fromkeys(VANBAN_FILE_LINK.findall(page)))}


def moj_document_numbers() -> set[str]:
    """Số hiệu (chuẩn hoá) của mọi văn bản đã tải từ Bộ Tư pháp — để biết nguồn khác có gì Bộ Tư pháp chưa có."""
    return {normalize_number(d.get("docNum") or "") for d in moj.load_saved_documents()} - {""}


def save_metadata(folder: Path, metadata: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=1), encoding="utf-8")


def discover_from_congbao(report: StageReport, known_numbers: set[str], not_on_moj: list[str]) -> None:
    rss = ET.fromstring(moj.http_get(CONGBAO_NEW_DOCUMENTS_RSS))
    items = rss.findall(".//item")
    last_run = (datetime.fromisoformat(CONGBAO_LAST_RUN_FILE.read_text(encoding="utf-8").strip())
                if CONGBAO_LAST_RUN_FILE.exists() else None)
    published = [parsedate_to_datetime(i.findtext("pubDate")) for i in items if i.findtext("pubDate")]
    # RSS chỉ giữ 50 mục: mục cũ nhất vẫn mới hơn lần chạy trước → có thể đã trôi mất văn bản ở giữa.
    if last_run and published and min(published) > last_run:
        report.count("rss_congbao_co_the_sot")
        log.warning("[congbao] cả %d mục RSS đều mới hơn lần chạy trước — có thể đã sót văn bản, nên chạy dày hơn",
                    len(items))
    jobs = []
    for item in items:
        summary = (item.findtext("description") or "").strip()
        congbao_id = (re.search(r"-(\d+)\.htm$", item.findtext("link") or "") or [None, None])[1]
        if not congbao_id or not TAX_WORDS.search(summary):
            continue
        report.count("congbao_van_ban_thue_trong_rss")
        folder = CONGBAO_NEW_DIR / congbao_id
        if (folder / "meta.json").exists():
            report.count("congbao_da_co")
            continue
        try:
            hit = next((h for h in search_congbao(summary) if str(h.get("id_van_ban")) == congbao_id), None)
        except Exception as e:  # một văn bản lỗi không chặn văn bản khác
            report.fail(f"[congbao] {congbao_id}", e, log)
            continue
        if hit is None:
            report.fail(f"[congbao] {congbao_id}", "API tìm kiếm không trả văn bản có mã này", log)
            continue
        number = hit.get("so_ky_hieu") or ""
        on_moj = normalize_number(number) in known_numbers
        report.count("da_co_tren_bo_tu_phap" if on_moj else "chua_co_tren_bo_tu_phap")
        save_metadata(folder, {"nguon": "congbao.chinhphu.vn", "rss": {"link": item.findtext("link"),
                      "pubDate": item.findtext("pubDate"), "description": summary}, "api": hit})
        if not on_moj:
            not_on_moj.append(f"[congbao] {number} — {summary[:80]}")
            for file in hit.get("danh_sach_tep_van_ban") or []:
                url = file["duong_dan"]
                name = f"{file.get('thu_tu', 0):02d}{Path(url).suffix.lower()}"
                jobs.append((folder / name, lambda url=url: moj.http_get(url), f"{congbao_id}/{name}"))
    moj.download_and_save(jobs, report, source="congbao")
    CONGBAO_LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONGBAO_LAST_RUN_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")


def discover_from_vanban_chinhphu(report: StageReport, known_numbers: set[str], not_on_moj: list[str]) -> None:
    VANBAN_DIR.mkdir(parents=True, exist_ok=True)
    if not VANBAN_LAST_DOCID_FILE.exists():
        # Lần đầu: bắt đầu từ docid mới nhất trên trang chủ — không dò ngược quá khứ (Bộ Tư pháp đã có lịch sử).
        newest = max(int(d) for d in DOCID_LINK.findall(moj.http_get(VANBAN_HOME).decode("utf-8", "replace")))
        VANBAN_LAST_DOCID_FILE.write_text(str(newest), encoding="utf-8")
        report.count("vanban_khoi_tao")
        log.info("[vanban_chinhphu] lần đầu: bắt đầu dò từ docid %d", newest)
        return
    last = int(VANBAN_LAST_DOCID_FILE.read_text(encoding="utf-8").strip())
    docid, empty_in_a_row, highest_found = last, 0, last
    while docid < last + VANBAN_MAX_DOCIDS_PER_RUN and empty_in_a_row < VANBAN_STOP_AFTER_EMPTY:
        docid += 1
        time.sleep(config.FETCH_DELAY_SECONDS)
        try:
            page = moj.http_get(VANBAN_DOCUMENT_URL.format(docid)).decode("utf-8", "replace")
        except Exception as e:
            report.fail(f"[vanban_chinhphu] docid {docid}", e, log)
            empty_in_a_row += 1
            continue
        document = parse_vanban_page(page)
        if document is None:
            empty_in_a_row += 1
            continue
        empty_in_a_row, highest_found = 0, docid
        report.count("vanban_van_ban_moi")
        if not TAX_WORDS.search(document["trich_yeu"]):
            continue
        report.count("vanban_van_ban_thue")
        on_moj = normalize_number(document["so_hieu"]) in known_numbers
        report.count("da_co_tren_bo_tu_phap" if on_moj else "chua_co_tren_bo_tu_phap")
        folder = VANBAN_DIR / str(docid)
        save_metadata(folder, {"nguon": "www.chinhphu.vn", "docid": docid, **document})
        if not on_moj:
            not_on_moj.append(f"[vanban_chinhphu] {document['so_hieu']} — {document['trich_yeu'][:80]}")
            moj.download_and_save(
                [(folder / Path(url).name, lambda url=url: moj.http_get(url), f"{docid}/{Path(url).name}")
                 for url in document["files"]], report, source="vanban_chinhphu")
    VANBAN_LAST_DOCID_FILE.write_text(str(highest_found), encoding="utf-8")


def discover_from_other_sources() -> tuple[StageReport, list[str]]:
    """Mỗi nguồn chạy riêng: nguồn chết (theo source_health) thì bỏ qua, nguồn còn lại vẫn chạy."""
    report = StageReport("nguon_khac")
    known_numbers = moj_document_numbers()
    not_on_moj: list[str] = []
    for name, discover in (("congbao", discover_from_congbao), ("vanban_chinhphu", discover_from_vanban_chinhphu)):
        if not is_source_alive(name):
            report.count(f"bo_qua_{name}_vi_nguon_chet")
            log.warning("[%s] bỏ qua — source_health báo nguồn chết", name)
            continue
        try:
            discover(report, known_numbers, not_on_moj)
        except Exception as e:  # cả nguồn hỏng giữa chừng: ghi lại, nguồn kia vẫn chạy
            report.fail(f"[{name}] cả nguồn", e, log)
    log.info(report.summary())
    return report, not_on_moj


def self_check() -> None:
    page = ("<html><td>Số ký hiệu</td><td>16767/BTC-ĐTPT</td><td>Ngày ban hành</td><td>20-10-2026</td>"
            "<td>Loại văn bản</td><td>Công văn</td><td>Cơ quan ban hành</td><td>Bộ Tài chính</td><td>Người ký</td>"
            "<td>Tạ Anh Tuấn</td><td>Trích yếu</td><td>V/v hoàn thuế giá trị gia tăng</td><td>Tài liệu đính kèm</td>"
            "<a href='https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/10/a.pdf'>a.pdf</a></html>")
    document = parse_vanban_page(page)
    assert document["so_hieu"] == "16767/BTC-ĐTPT", document
    assert document["trich_yeu"] == "V/v hoàn thuế giá trị gia tăng", document
    assert document["files"] == ["https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/10/a.pdf"], document
    assert parse_vanban_page("<html>Trang không có văn bản</html>") is None
    assert TAX_WORDS.search(document["trich_yeu"])
    print("PASS")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    report, not_on_moj = discover_from_other_sources()
    print(report.summary())
    for line in not_on_moj:
        print("  chưa có trên Bộ Tư pháp:", line)


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

"""Tải văn bản thuế về đĩa: danh sách lấy từ sitemap vbpl.vn, nội dung lấy từ cổng JSON Bộ Tư pháp.

Chạy:
    python -m app.ingest.download_moj_documents           chạy cả ba công đoạn bên dưới
    python -m app.ingest.download_moj_documents --check   tự kiểm, không gọi mạng
Trong pipeline, Dagster gọi từng công đoạn riêng (app/pipeline/definitions.py).

Ba công đoạn, mỗi cái trả về một StageReport:
    update_document_list()   sitemap → data/raw/moj/sitemap.tsv (id → link vbpl.vn, chỉ thêm, không xoá)
    download_documents()     JSON của văn bản mới + tải lại văn bản thuế còn hiệu lực
                             → data/raw/moj/{id}.json; bản cũ bị cổng sửa → history/{id}/{thời điểm}.json
    download_attachments()   PDF/DOC của văn bản mà JSON không có chữ → data/raw/moj/files/{id}/{tên file}
                             file máy chủ báo không có (404) ghi vào files/missing.txt, không thử lại

Một văn bản lỗi chỉ được ghi vào báo cáo, công đoạn chạy tiếp. Công đoạn chỉ dừng (báo
SourceUnavailableError) khi lỗi liên tiếp nhiều lần — cổng có thể đang tắt hoặc chặn mình.
"""

import hashlib
import html
import json
import logging
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app import config
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

SITEMAP_INDEX_URL = "https://vbpl.vn/sitemap.xml"
MOJ_DOCUMENT_API = "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/"
# Đường chính trang vbpl.vn dùng để hiện file đính kèm (tìm thấy trong JS của trang).
MOJ_ATTACHMENT_API = MOJ_DOCUMENT_API + "minio/buckets/vbpl/"
# Theo chú thích trong sitemap.xml: file 1–12 là văn bản trung ương, 13–36 là địa phương.
CENTRAL_GOVERNMENT_SITEMAPS = range(1, 13)

MOJ_RAW_DIR = config.RAW_DATA_DIR / "moj"
SOURCE_URLS_FILE = MOJ_RAW_DIR / "sitemap.tsv"
ATTACHMENTS_DIR = MOJ_RAW_DIR / "files"
# Mỗi dòng "{id}/{tên file}" mà máy chủ trả 404 — chủ yếu file .doc của văn bản trước 2003.
MISSING_ATTACHMENTS_FILE = ATTACHMENTS_DIR / "missing.txt"
# Hiệu lực trên cổng: hết hiệu lực / tạm ngưng — không tải lại, không đi tìm ở nguồn khác.
EXPIRED_STATUS_CODES = {"HHL", "TNHL"}

# Bấy nhiêu lỗi liên tiếp thì coi như cổng sập hoặc đang chặn mình → dừng công đoạn.
MAX_CONSECUTIVE_FAILURES = 10
# Lỗi mạng tạm thời: thử lại sau 5 giây rồi 15 giây. Lỗi 4xx (trừ 429) là lỗi thật, không thử lại.
RETRY_WAIT_SECONDS = (5, 15)
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

# Lọc thô trên link (không dấu) nên "thue" khớp cả "thuê bao", "cho thuê".
TAX_WORDS_IN_URL = re.compile(r"thue|hoa-don")
# Lọc chính xác, có dấu. "hóa"/"hoá" là hai cách bỏ dấu đều gặp trong văn bản thật.
TAX_WORDS_IN_TITLE = re.compile(r"thuế|hóa đơn|hoá đơn", re.IGNORECASE)
# Chỉ chấp nhận đúng hai dạng ID đã thấy — ID đi thẳng vào tên file.
VALID_DOCUMENT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+")
SITEMAP_XML_NAMESPACE = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# Những trường mà đổi thì coi là văn bản đã bị sửa. Các trường như reviewStatus đổi liên tục
# mà không đổi nội dung (đo 15/10/2026) nên không tính.
SIGNIFICANT_FIELDS = (
    "title", "docNum", "docType", "issueDate", "effFrom", "effTo", "effStatus",
    "documentFields", "documentContent", "documentContentFileName", "documentContentFileDocName",
)


class SourceUnavailableError(RuntimeError):
    """Nguồn dữ liệu có vẻ đang sập hoặc chặn truy cập — dừng công đoạn, chạy lại sau."""


def document_id_from_url(url: str) -> str | None:
    """Link vbpl.vn có dạng .../chi-tiet/{slug}--{id}. ID là số (văn bản cũ) hoặc UUID."""
    tail = url.rsplit("--", 1)[-1]
    return tail if "--" in url and VALID_DOCUMENT_ID.fullmatch(tail) else None


def is_tax_document(doc: dict) -> bool:
    """Văn bản thuế nếu tiêu đề hoặc lĩnh vực nhắc tới thuế/hóa đơn.

    Cần cả hai: văn bản mới có trường lĩnh vực nhưng tiêu đề có thể không nhắc thuế;
    văn bản cũ thì lĩnh vực để trống.
    """
    texts = [doc.get("title") or ""] + [f.get("name") or "" for f in doc.get("documentFields") or []]
    return any(TAX_WORDS_IN_TITLE.search(unicodedata.normalize("NFC", t)) for t in texts)


def is_in_force(doc: dict) -> bool:
    return (doc.get("effStatus") or {}).get("code") not in EXPIRED_STATUS_CODES


def has_text_content(doc: dict) -> bool:
    """22% văn bản trên cổng chỉ có khung HTML trống — chữ nằm trong file đính kèm."""
    content = (doc.get("documentContent") or {}).get("content") or ""
    return len(html.unescape(re.sub(r"<[^>]+>", " ", content)).split()) >= 30


def safe_attachment_names(doc: dict) -> list[str]:
    """Tên file PDF/DOC của văn bản. Tên đi vào đường dẫn trên đĩa → loại tên có thư mục."""
    names = [doc.get("documentContentFileName"), doc.get("documentContentFileDocName")]
    return [n for n in names if n and not re.search(r"[\\/:*?\"<>|]|^\.|\.\.", n)]


def document_fingerprint(body: bytes) -> str:
    """Dấu vân tay của những trường có ý nghĩa — giống nhau nghĩa là văn bản chưa bị sửa."""
    data = json.loads(body)["data"]
    significant = {k: data.get(k) for k in SIGNIFICANT_FIELDS}
    return hashlib.sha256(json.dumps(significant, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def http_request(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    """GET (hoặc POST khi có data). Lỗi mạng tạm thời và 429/5xx được thử lại."""
    headers = {"User-Agent": config.FETCH_USER_AGENT}
    if content_type:
        headers["Content-Type"] = content_type
    for attempt in range(len(RETRY_WAIT_SECONDS) + 1):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_HTTP_CODES or attempt == len(RETRY_WAIT_SECONDS):
                raise
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == len(RETRY_WAIT_SECONDS):
                raise
            reason = f"{type(e).__name__}: {e}"
        log.info("thử lại sau %ss (%s): %s", RETRY_WAIT_SECONDS[attempt], reason, url)
        time.sleep(RETRY_WAIT_SECONDS[attempt])
    raise AssertionError("không tới được đây")


def http_get(url: str) -> bytes:
    return http_request(url)


def fetch_document_json(doc_id: str) -> bytes:
    """JSON thô của cổng. Lỗi nếu cổng báo thất bại — không lưu bản rác."""
    try:
        body = http_get(MOJ_DOCUMENT_API + doc_id)
    except urllib.error.HTTPError as e:
        # Cổng trả 400 kèm JSON lý do, ví dụ "invalid.document.entity.not.found".
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from e
    parsed = json.loads(body)
    if parsed.get("success") is not True or not parsed.get("data"):
        raise RuntimeError(f"cổng báo lỗi: {parsed.get('messageCode')}")
    return body


def fetch_attachment(doc_id: str, file_name: str) -> bytes:
    try:
        return http_get(f"{MOJ_ATTACHMENT_API}{doc_id}/{urllib.parse.quote(file_name)}/download")
    except urllib.error.HTTPError as e:
        if e.code == 404:  # file .doc của văn bản cũ thường không có trên máy chủ
            raise FileNotFoundError("máy chủ không có file này") from e
        raise


def _write_atomically(path: Path, body: bytes) -> None:
    """Ghi ra file tạm rồi đổi tên: bị ngắt giữa chừng không để lại file cụt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_bytes(body)
    temp_path.replace(path)


def _archive_old_version(path: Path) -> Path:
    """Chuyển bản cũ vào history/{tên file}/{thời điểm}{đuôi} cạnh nó. Không bao giờ xoá bản gốc."""
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    archived = path.parent / "history" / path.stem / f"{stamp}{path.suffix}"
    archived.parent.mkdir(parents=True, exist_ok=True)
    path.replace(archived)
    return archived


def download_and_save(
    jobs: list[tuple[Path, Callable[[], bytes], str]],
    report: StageReport,
    missing_file: Path | None = None,
    fingerprint: Callable[[bytes], str] | None = None,
    delay_seconds: float | None = None,
) -> None:
    """Tải từng (nơi lưu, hàm tải, nhãn), cách nhau FETCH_DELAY_SECONDS. Dùng chung cho mọi bộ tải.

    - File đã có và có `fingerprint`: so dấu vân tay; giống thì bỏ qua, khác thì bản cũ vào history/.
    - Máy chủ báo không có file (FileNotFoundError): ghi vào `missing_file`, đi tiếp.
    - Lỗi khác: ghi vào báo cáo, đi tiếp; MAX_CONSECUTIVE_FAILURES lỗi liên tiếp → SourceUnavailableError.
    """
    delay = config.FETCH_DELAY_SECONDS if delay_seconds is None else delay_seconds
    failures_in_a_row = 0
    started = time.monotonic()
    for n, (save_path, fetch, label) in enumerate(jobs, 1):
        time.sleep(delay)
        try:
            body = fetch()
            if fingerprint and save_path.exists():
                if fingerprint(body) == fingerprint(save_path.read_bytes()):
                    report.count("khong_doi")
                else:
                    archived = _archive_old_version(save_path)
                    _write_atomically(save_path, body)
                    report.count("thay_doi")
                    log.info("THAY ĐỔI %s — bản cũ: %s", label, archived.name)
            else:
                _write_atomically(save_path, body)
                report.count("tai_moi")
            failures_in_a_row = 0
        except FileNotFoundError as e:
            report.count("khong_co_tren_may_chu")
            log.info("THIẾU %s: %s", label, e)
            if missing_file:
                missing_file.parent.mkdir(parents=True, exist_ok=True)
                with missing_file.open("a", encoding="utf-8") as f:
                    f.write(label + "\n")
        except Exception as e:  # mạng, JSON hỏng, cổng báo lỗi — ghi lại rồi đi tiếp
            report.fail(label, e, log)
            failures_in_a_row += 1
            if failures_in_a_row >= MAX_CONSECUTIVE_FAILURES:
                raise SourceUnavailableError(
                    f"{failures_in_a_row} lỗi liên tiếp — nguồn có thể đang tắt hoặc chặn. "
                    f"Đã làm được: {report.summary()}"
                ) from e
        if n % 100 == 0:
            minutes_left = (time.monotonic() - started) / n * (len(jobs) - n) / 60
            log.info("%d/%d — còn khoảng %.0f phút — %s", n, len(jobs), minutes_left, report.summary())


def read_source_urls() -> dict[str, str]:
    """id văn bản → link vbpl.vn (dùng làm link bản gốc khi trích dẫn)."""
    if not SOURCE_URLS_FILE.exists():
        return {}
    lines = SOURCE_URLS_FILE.read_text(encoding="utf-8").splitlines()
    return dict(line.split("\t", 1) for line in lines if "\t" in line)


def load_saved_documents(report: StageReport | None = None) -> list[dict]:
    """Mọi văn bản đã tải (phần "data" của JSON cổng). File hỏng thì ghi lỗi và bỏ qua."""
    docs = []
    for path in sorted(MOJ_RAW_DIR.glob("*.json")):
        try:
            docs.append(json.loads(path.read_bytes())["data"])
        except Exception as e:
            if report:
                report.fail(path.name, e, log)
            else:
                log.warning("bỏ qua file hỏng %s: %s", path.name, e)
    return docs


def load_saved_tax_documents(report: StageReport | None = None) -> list[dict]:
    return [d for d in load_saved_documents(report) if is_tax_document(d)]


def update_document_list() -> StageReport:
    """Đọc sitemap trung ương, gộp ứng viên mới vào sitemap.tsv. Không xoá dòng cũ:
    văn bản bị gỡ khỏi sitemap vẫn giữ link gốc để trích dẫn."""
    report = StageReport("danh_sach_van_ban")
    try:
        index = http_get(SITEMAP_INDEX_URL).decode()
    except Exception as e:
        raise SourceUnavailableError(f"không đọc được {SITEMAP_INDEX_URL}: {e}") from e
    numbers = [n for n in re.findall(r"https://vbpl\.vn/sitemap/(\d+)\.xml", index)
               if int(n) in CENTRAL_GOVERNMENT_SITEMAPS]
    found: dict[str, str] = {}
    for n in numbers:
        time.sleep(config.FETCH_DELAY_SECONDS)
        try:
            root = ET.fromstring(http_get(f"https://vbpl.vn/sitemap/{n}.xml"))
        except Exception as e:
            report.fail(f"sitemap/{n}.xml", e, log)
            continue
        for loc in root.iterfind("s:url/s:loc", SITEMAP_XML_NAMESPACE):
            url = loc.text.strip()
            doc_id = document_id_from_url(url)
            if doc_id and TAX_WORDS_IN_URL.search(url):
                found.setdefault(doc_id, url)
        log.info("sitemap %s.xml: %d ứng viên", n, len(found))
    if report.failure_count == len(numbers):
        raise SourceUnavailableError("không đọc được sitemap nào")

    known = read_source_urls()
    report.count("ung_vien_trong_sitemap", len(found))
    report.count("ung_vien_moi", len(found.keys() - known.keys()))
    merged = {**known, **found}
    MOJ_RAW_DIR.mkdir(parents=True, exist_ok=True)
    _write_atomically(SOURCE_URLS_FILE, "".join(f"{i}\t{u}\n" for i, u in merged.items()).encode("utf-8"))
    report.count("tong_trong_danh_sach", len(merged))
    log.info(report.summary())
    return report


def download_documents() -> StageReport:
    """Tải JSON của văn bản chưa có, và tải lại văn bản thuế còn hiệu lực để bắt chỗ cổng đã sửa."""
    report = StageReport("van_ban_bo_tu_phap")
    candidates = read_source_urls()
    new_ids = [i for i in candidates if not (MOJ_RAW_DIR / f"{i}.json").exists()]
    refresh_ids = [d["id"] for d in load_saved_tax_documents(report)
                   if is_in_force(d) and VALID_DOCUMENT_ID.fullmatch(d["id"])]
    log.info("văn bản mới cần tải: %d; văn bản còn hiệu lực cần tải lại: %d", len(new_ids), len(refresh_ids))
    download_and_save(
        [(MOJ_RAW_DIR / f"{i}.json", lambda i=i: fetch_document_json(i), i) for i in new_ids + refresh_ids],
        report,
        fingerprint=document_fingerprint,
    )
    log.info(report.summary())
    return report


def download_attachments() -> StageReport:
    """Tải PDF/DOC cho văn bản thuế mà JSON không có chữ. File 404 đã biết thì không thử lại."""
    report = StageReport("file_dinh_kem")
    attachments = [
        (ATTACHMENTS_DIR / d["id"] / name, d["id"], name)
        for d in load_saved_tax_documents(report) if not has_text_content(d) and VALID_DOCUMENT_ID.fullmatch(d["id"])
        for name in safe_attachment_names(d)
    ]
    # Xoá missing.txt để thử lại tất cả.
    known_missing = (set(MISSING_ATTACHMENTS_FILE.read_text(encoding="utf-8").splitlines())
                     if MISSING_ATTACHMENTS_FILE.exists() else set())
    to_download = [a for a in attachments if not a[0].exists() and f"{a[1]}/{a[2]}" not in known_missing]
    report.count("da_co", sum(a[0].exists() for a in attachments))
    log.info("file đính kèm: %d, đã có %d, đã biết máy chủ không có %d, cần tải %d",
             len(attachments), report.counts["da_co"], len(known_missing), len(to_download))
    download_and_save(
        [(path, lambda i=i, n=n: fetch_attachment(i, n), f"{i}/{n}") for path, i, n in to_download],
        report,
        missing_file=MISSING_ATTACHMENTS_FILE,
    )
    log.info(report.summary())
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for stage in (update_document_list, download_documents, download_attachments):
        report = stage()
        print(report.summary(), flush=True)


def self_check() -> None:
    base = "https://vbpl.vn/van-ban/chi-tiet/"
    assert document_id_from_url(base + "luat-quan-ly-thue-so-108-2025-qh15--187043") == "187043"
    uuid = "de1284f0-b0b9-11f1-bafa-e53f8f5caa8a"
    assert document_id_from_url(base + "thong-tu-so-136-2026-tt-btc--" + uuid) == uuid
    assert document_id_from_url(base + "khong-co-id") is None
    assert document_id_from_url(base + "x--..\\..\\windows") is None, "ID lạ không được thành tên file"

    assert is_tax_document({"title": "Luật Quản lý thuế số 108/2025/QH15", "documentFields": []})
    assert is_tax_document({"title": "Nghị định quy định về hoá đơn, chứng từ"})
    assert is_tax_document({"title": unicodedata.normalize("NFD", "Luật Thuế giá trị gia tăng")}), "chữ tổ hợp"
    assert is_tax_document({"title": "Thông tư 136/2026", "documentFields": [{"name": "Thuế tiêu thụ đặc biệt"}]})
    assert not is_tax_document({"title": "Hướng dẫn xác thực thông tin thuê bao di động", "documentFields": None})
    assert not is_tax_document({"title": "Khung giá cho thuê nhà lưu trú công nhân"})
    assert is_in_force({"effStatus": {"code": "CHL"}}) and not is_in_force({"effStatus": {"code": "HHL"}})

    # Đúng khung HTML rỗng 83 ký tự thấy trên cổng.
    assert not has_text_content({"documentContent": {"content": "<html>\n <head></head>\n <body>\n </body>\n</html>"}})
    assert not has_text_content({"documentContent": None})
    assert has_text_content({"documentContent": {"content": "<p>" + "Điều 1. Phạm vi điều chỉnh " * 10 + "</p>"}})

    assert safe_attachment_names({"documentContentFileName": "VanBanGoc_125.2016.NĐ.CP.pdf",
                                  "documentContentFileDocName": None}) == ["VanBanGoc_125.2016.NĐ.CP.pdf"]
    for bad in ["../x.pdf", "a/b.pdf", "a\\b.doc", "C:x.pdf", ".hidden"]:
        assert safe_attachment_names({"documentContentFileName": bad}) == [], bad

    def doc_json(content: str, review: str = "a") -> bytes:
        return json.dumps({"data": {"documentContent": {"content": content}, "reviewStatus": review}}).encode()

    assert document_fingerprint(doc_json("x", "a")) == document_fingerprint(doc_json("x", "b")), \
        "reviewStatus đổi không phải là văn bản bị sửa"
    assert document_fingerprint(doc_json("x")) != document_fingerprint(doc_json("y"))

    logging.getLogger(__name__).disabled = True
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        target, missing = folder / "1.json", folder / "missing.txt"

        def fail():
            raise RuntimeError("cổng lỗi")

        def gone():
            raise FileNotFoundError("404")

        report = StageReport("thử")
        download_and_save([(target, lambda: doc_json("x"), "1")], report, fingerprint=document_fingerprint, delay_seconds=0)
        download_and_save([(target, lambda: doc_json("x", "đổi"), "1")], report, fingerprint=document_fingerprint, delay_seconds=0)
        assert report.counts == {"tai_moi": 1, "khong_doi": 1} and not (folder / "history").exists()
        download_and_save([(target, lambda: doc_json("đã sửa"), "1")], report, fingerprint=document_fingerprint, delay_seconds=0)
        assert report.counts["thay_doi"] == 1
        assert json.loads(target.read_bytes())["data"]["documentContent"]["content"] == "đã sửa"
        archived = list((folder / "history" / "1").iterdir())
        assert len(archived) == 1 and b'"x"' in archived[0].read_bytes(), "bản cũ phải được giữ"

        report = StageReport("thử")
        download_and_save([(folder / "2.pdf", fail, "2"), (folder / "3.pdf", gone, "3"),
                           (folder / "4.pdf", lambda: b"ok", "4")], report, missing_file=missing, delay_seconds=0)
        assert report.failure_count == 1 and report.counts["khong_co_tren_may_chu"] == 1
        assert report.counts["tai_moi"] == 1, "một lỗi không được chặn văn bản sau"
        assert missing.read_text(encoding="utf-8") == "3\n"

        report = StageReport("thử")
        try:
            download_and_save([(folder / f"{n}.pdf", fail, str(n)) for n in range(MAX_CONSECUTIVE_FAILURES + 5)],
                              report, delay_seconds=0)
            raise AssertionError("phải dừng khi lỗi liên tiếp")
        except SourceUnavailableError:
            assert report.failure_count == MAX_CONSECUTIVE_FAILURES
    print("PASS")


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

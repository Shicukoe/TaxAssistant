"""Nguồn dự phòng: lấy từ congbao.chinhphu.vn những văn bản thuế mà cổng Bộ Tư pháp không có chữ
và không có file đính kèm (xem docs/nguon-du-lieu.md).

Chạy sau download_moj_documents (trong pipeline: công đoạn download_missing_from_congbao):
    python -m app.ingest.download_from_congbao           tìm + tải văn bản còn thiếu
    python -m app.ingest.download_from_congbao --check   tự kiểm phần khớp văn bản, không gọi mạng

Lưu ra data/raw/congbao/{id cổng Bộ Tư pháp}/:
    meta.json     kết quả tìm kiếm khớp, nguyên văn — có link, số công báo để ghi nguồn
    01.pdf, 02.doc ...   file theo thứ tự của congbao; một văn bản hợp nhất dài có thể
                         bị chia qua nhiều số công báo nên có nhiều cặp pdf/doc
data/raw/congbao/missing.txt   file congbao báo không có (404) — không thử lại
Một văn bản lỗi (tìm hoặc tải) chỉ được ghi vào báo cáo, công đoạn chạy tiếp.
Bắt buộc ghi nguồn "congbao.chinhphu.vn" khi trích dẫn.
"""

import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
from datetime import date

from app import config
from app.ingest import download_moj_documents as moj
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

# API trang tìm kiếm của congbao.chinhphu.vn dùng (tìm thấy trong JS của trang). Không CAPTCHA.
CONGBAO_SEARCH_API = "https://api-searchcongbao.chinhphu.vn/search/van-ban"
CONGBAO_RAW_DIR = config.RAW_DATA_DIR / "congbao"
MISSING_FILES = CONGBAO_RAW_DIR / "missing.txt"


def documents_missing_from_moj(report: StageReport | None = None) -> list[dict]:
    """Văn bản thuế chưa hết hiệu lực mà cổng Bộ Tư pháp không có chữ, cũng không có file."""
    return [
        d for d in moj.load_saved_tax_documents(report)
        if not moj.has_text_content(d)
        and not any((moj.ATTACHMENTS_DIR / d["id"] / n).exists() for n in moj.safe_attachment_names(d))
        and moj.is_in_force(d)
        and (d.get("docType") or {}).get("name") != "Công văn"  # công văn không đăng công báo
    ]


def _number_without_year(doc_number: str) -> str:
    """Số hiệu không năm, viết hoa: '31/2017/TT-BTC' và '31/TT-BTC' cùng thành '31/TT-BTC'.

    Cổng Bộ Tư pháp đôi khi ghi thiếu năm trong số hiệu.
    """
    return re.sub(r"/(19|20)\d\d/", "/", doc_number.strip().upper())


def is_same_document(moj_doc: dict, congbao_hit: dict) -> bool:
    """Cùng số hiệu và ngày ban hành lệch không quá 1 ngày.

    Số hiệu văn bản hợp nhất lặp lại mỗi năm (03/VBHN-BCT có ở 2013, 2014, ... 2026) nên
    phải so cả ngày. Hai nguồn lệch nhau 1 ngày ở một số văn bản (23/01 vs 24/01/2014).
    """
    if _number_without_year(congbao_hit.get("so_ky_hieu") or "") != _number_without_year(moj_doc["docNum"]):
        return False
    a = (moj_doc.get("issueDate") or "")[:10]
    b = (congbao_hit.get("ngay_ban_hanh") or "")[:10]
    return bool(a and b) and abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= 1


def search_terms_for(moj_doc: dict) -> list[str]:
    """Tìm theo số hiệu; nếu số hiệu thiếu năm (không phải văn bản hợp nhất) thử thêm bản có năm."""
    number, year = moj_doc["docNum"], (moj_doc.get("issueDate") or "")[:4]
    if re.search(r"/(19|20)\d\d/", number) or "VBHN" in number.upper() or not year:
        return [number]
    head, _, tail = number.partition("/")
    return [number, f"{head}/{year}/{tail}"]


def search_congbao(term: str) -> list[dict]:
    body = moj.http_request(
        CONGBAO_SEARCH_API,
        data=json.dumps({"filters": {}, "page": 1, "page_size": 20, "query": term}).encode(),
        content_type="application/json",
    )
    return json.loads(body).get("data") or []


def fetch_congbao_file(url: str) -> bytes:
    try:
        return moj.http_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError("congbao không có file này") from e
        raise


def attachment_download_jobs(doc_id: str, congbao_hit: dict) -> list:
    """Việc tải cho moj.download_and_save. Chỉ nhận link http/https thuộc *.chinhphu.vn."""
    jobs = []
    files = sorted(congbao_hit.get("danh_sach_tep_van_ban") or [], key=lambda f: f.get("thu_tu") or 0)
    for f in files:
        url = f.get("duong_dan") or ""
        parts = urllib.parse.urlsplit(url)
        # Trường file_extension có lúc là rác → lấy đuôi từ link. Link cũ viết dính
        # không có dấu chấm: ".../1807-1-2014173-174-03vbhn-bctpdf" (vẫn là PDF thật).
        m = re.search(r"\.?(pdf|docx|doc)$", parts.path.lower())
        extension = m.group(1) if m else ""
        host = parts.hostname or ""
        trusted = host == "chinhphu.vn" or host.endswith(".chinhphu.vn")
        if parts.scheme not in ("http", "https") or not trusted or not extension:
            log.warning("BỎ link lạ %s: %s", doc_id, url)
            continue
        save_path = CONGBAO_RAW_DIR / doc_id / f"{f.get('thu_tu') or len(jobs) + 1:02d}.{extension}"
        if not save_path.exists():
            jobs.append((save_path, lambda url=url: fetch_congbao_file(url), f"{doc_id}/{save_path.name}"))
    return jobs


def download_missing_from_congbao() -> StageReport:
    """Tìm trên congbao văn bản cổng Bộ Tư pháp thiếu, lưu kết quả khớp và tải file."""
    report = StageReport("congbao")
    to_find = [d for d in documents_missing_from_moj(report)
               if not (CONGBAO_RAW_DIR / d["id"] / "meta.json").exists()]
    log.info("văn bản cần tìm trên congbao: %d", len(to_find))
    jobs = []
    for d in to_find:
        label = f"{d.get('docNum')} ({(d.get('issueDate') or '')[:10]})"
        try:
            hit = None
            for term in search_terms_for(d):
                time.sleep(config.FETCH_DELAY_SECONDS)
                hit = next((h for h in search_congbao(term) if is_same_document(d, h)), None)
                if hit:
                    break
        except Exception as e:  # một lần tìm lỗi không được chặn các văn bản khác
            report.fail(label, e, log)
            continue
        if not hit:
            report.count("khong_thay")
            log.info("KHÔNG THẤY %s %s", label, (d.get("title") or "")[:60])
            continue
        report.count("tim_thay")
        folder = CONGBAO_RAW_DIR / d["id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "meta.json").write_text(json.dumps(hit, ensure_ascii=False, indent=1), encoding="utf-8")
        jobs += attachment_download_jobs(d["id"], hit)

    # File của văn bản đã tìm thấy ở lần trước nhưng tải dở. File congbao báo 404 thì không thử lại.
    just_found = {d["id"] for d in to_find}
    for meta in CONGBAO_RAW_DIR.glob("*/meta.json"):
        if meta.parent.name not in just_found:
            try:
                jobs += attachment_download_jobs(meta.parent.name, json.loads(meta.read_text(encoding="utf-8")))
            except Exception as e:
                report.fail(str(meta.relative_to(CONGBAO_RAW_DIR)), e, log)
    known_missing = set(MISSING_FILES.read_text(encoding="utf-8").splitlines()) if MISSING_FILES.exists() else set()
    jobs = [j for j in jobs if j[2] not in known_missing]
    log.info("cần tải %d file", len(jobs))
    moj.download_and_save(jobs, report, missing_file=MISSING_FILES)
    log.info(report.summary())
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(download_missing_from_congbao().summary())


def self_check() -> None:
    d = {"docNum": "03/VBHN-BCT", "issueDate": "2014-01-24T00:00:00"}
    assert is_same_document(d, {"so_ky_hieu": "03/VBHN-BCT", "ngay_ban_hanh": "2014-01-23T00:00:00"}), "lệch 1 ngày"
    assert not is_same_document(d, {"so_ky_hieu": "03/VBHN-BCT", "ngay_ban_hanh": "2026-01-23T00:00:00"}), "khác năm"
    assert not is_same_document(d, {"so_ky_hieu": "03/VBHN-BGTVT", "ngay_ban_hanh": "2014-01-24T00:00:00"})

    tt = {"docNum": "31/TT-BTC", "issueDate": "2017-04-18T00:00:00"}
    assert search_terms_for(tt) == ["31/TT-BTC", "31/2017/TT-BTC"]
    assert is_same_document(tt, {"so_ky_hieu": "31/2017/TT-BTC", "ngay_ban_hanh": "2017-04-18T00:00:00"})
    assert search_terms_for({"docNum": "03/VBHN-VPQH", "issueDate": "2024-09-16T00:00:00"}) == ["03/VBHN-VPQH"]

    def jobs_for(*links):
        return attachment_download_jobs("x", {"danh_sach_tep_van_ban": list(links)})

    good = {"thu_tu": 2, "duong_dan": "https://congbaocdn.chinhphu.vn/1/2026/2/26/03signed-1.pdf"}
    foreign = {"thu_tu": 1, "duong_dan": "https://evil.example/a.pdf"}
    assert [j[0].name for j in jobs_for(good, foreign)] == ["02.pdf"], "chỉ nhận link chinhphu.vn"
    old = {"thu_tu": 1, "duong_dan": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2014/1/4084/1807-1-03vbhn-bctpdf"}
    assert [j[0].name for j in jobs_for(old)] == ["01.pdf"], "link cũ không có dấu chấm"
    lookalike = {"thu_tu": 1, "duong_dan": "https://evilchinhphu.vn/a.pdf"}
    assert jobs_for(lookalike) == [], "tên miền giả"
    print("PASS")


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

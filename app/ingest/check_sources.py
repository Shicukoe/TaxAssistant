"""Bảng nguồn dữ liệu + kiểm sống từng trang. Debug phải biết TRANG NÀO hỏng.

Chạy (trong pipeline: công đoạn source_health, chạy đầu tiên):
    python -m app.ingest.check_sources
    python -m app.ingest.check_sources --check     (bài tự kiểm, không gọi mạng)

Mỗi nguồn có một hàm kiểm sống gọi MỘT yêu cầu nhỏ và kiểm cả NỘI DUNG trả về — hỏng thường gặp là
"vẫn trả 200 nhưng nội dung khác" (tường lửa trả trang chặn, API đổi định dạng), không chỉ là mất kết nối.
Kết quả gần nhất ghi vào data/raw/source_health.json; các công đoạn tải đọc file này để biết nguồn nào đang chết.
Thêm nguồn mới = thêm một dòng vào SOURCES kèm hàm kiểm sống (docs/code-standards.md).
"""

import json
import logging
import sys
import time
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse

from app import config
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

HEALTH_FILE = config.RAW_DATA_DIR / "source_health.json"
VANBAN_DOCUMENT_URL = "https://vanban.chinhphu.vn/?pageid=27160&docid={}"
CONGBAO_NEW_DOCUMENTS_RSS = "https://congbao.chinhphu.vn/cac-van-ban-moi-ban-hanh.rss"


@dataclass(frozen=True)
class Source:
    name: str
    role: str  # nguồn này dùng vào việc gì
    hosts: tuple[str, ...]  # tên máy chủ thuộc nguồn này — để gắn tên nguồn vào lỗi mạng
    attribution: str | None  # bắt buộc ghi nguồn khi dùng (docs/nguon-du-lieu.md)


SOURCES = {
    "vbpl_sitemap": Source("vbpl_sitemap", "phát hiện văn bản mới (nguồn chính)", ("vbpl.vn",), None),
    "moj_gateway": Source("moj_gateway", "chữ văn bản + file đính kèm (nguồn chính)",
                          ("vbpl-bientap-gateway.moj.gov.vn",), None),
    "congbao": Source("congbao", "phát hiện văn bản mới (RSS) + bản gốc Word/PDF (dự phòng)",
                      ("congbao.chinhphu.vn", "api-searchcongbao.chinhphu.vn", "congbaocdn.chinhphu.vn"),
                      "congbao.chinhphu.vn"),
    "vanban_chinhphu": Source("vanban_chinhphu", "phát hiện văn bản mới + bản gốc (dự phòng thứ hai, có công văn BTC)",
                              ("vanban.chinhphu.vn", "datafiles.chinhphu.vn"), "www.chinhphu.vn"),
    "gdt": Source("gdt", "công văn của cơ quan thuế (đang bị tường lửa chặn script)", ("gdt.gov.vn",),
                  "gdt.gov.vn"),
}


def source_name_for_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for source in SOURCES.values():
        if any(host == h or host.endswith("." + h) for h in source.hosts):
            return source.name
    return host or "?"


# ---------------------------------------------------------------- hàm kiểm sống (mỗi nguồn một hàm)
# Trả về mô tả ngắn khi đạt; nội dung sai thì raise ContentMismatch với lý do.

class ContentMismatch(RuntimeError):
    """Trang trả lời được nhưng nội dung không như mong đợi (bị chặn, đổi định dạng)."""


def _get(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    from app.ingest.download_moj_documents import http_request  # import muộn: tránh vòng import
    return http_request(url, data=data, content_type=content_type)


def probe_vbpl_sitemap() -> str:
    from app.ingest.download_moj_documents import SITEMAP_INDEX_URL
    root = ET.fromstring(_get(SITEMAP_INDEX_URL))
    count = sum(1 for element in root.iter() if element.tag.endswith("loc"))
    if count == 0:
        raise ContentMismatch("sitemap.xml không còn thẻ <loc> nào")
    return f"{count} sitemap con"


def probe_moj_gateway() -> str:
    from app.ingest.download_moj_documents import MOJ_DOCUMENT_API
    body = json.loads(_get(MOJ_DOCUMENT_API + "10042"))  # văn bản cũ, ổn định: Thông tư 85-BTC/TCT
    title = (body.get("data") or {}).get("title")
    if not body.get("success") or not title:
        raise ContentMismatch(f"JSON không đúng khuôn: success={body.get('success')}, title={title!r}")
    return "JSON đúng khuôn"


def probe_congbao() -> str:
    from app.ingest.download_from_congbao import search_congbao
    hits = search_congbao("125/2020/NĐ-CP")
    if not any("125/2020" in (h.get("so_ky_hieu") or "") for h in hits):
        raise ContentMismatch(f"API tìm kiếm không còn trả văn bản đã biết ({len(hits)} kết quả)")
    items = ET.fromstring(_get(CONGBAO_NEW_DOCUMENTS_RSS)).findall(".//item")
    if not items:
        raise ContentMismatch("RSS văn bản mới không có mục nào")
    return f"API tìm kiếm + RSS ({len(items)} mục)"


def probe_vanban_chinhphu() -> str:
    page = _get(VANBAN_DOCUMENT_URL.format(220054)).decode("utf-8", errors="replace")
    if "Số ký hiệu" not in page:
        raise ContentMismatch("trang chi tiết văn bản không còn mục 'Số ký hiệu'")
    return "trang chi tiết đúng khuôn"


def probe_gdt() -> str:
    page = _get("https://gdt.gov.vn/").decode("utf-8", errors="replace")
    if "Request Rejected" in page:
        raise ContentMismatch("tường lửa chặn ('Request Rejected')")
    return "trang chủ mở được"


PROBES: dict[str, Callable[[], str]] = {
    "vbpl_sitemap": probe_vbpl_sitemap,
    "moj_gateway": probe_moj_gateway,
    "congbao": probe_congbao,
    "vanban_chinhphu": probe_vanban_chinhphu,
    "gdt": probe_gdt,
}


def check_sources() -> tuple[StageReport, dict[str, dict]]:
    """Kiểm mọi nguồn; một nguồn hỏng không chặn việc kiểm nguồn khác."""
    report = StageReport("kiem_nguon")
    results = {}
    for name, probe in PROBES.items():
        started = time.monotonic()
        result = {"nguon": name, "vai_tro": SOURCES[name].role, "kiem_luc": datetime.now().isoformat(timespec="seconds")}
        try:
            result.update(song=True, chi_tiet=probe())
            report.count("nguon_song")
        except urllib.error.HTTPError as e:
            result.update(song=False, chi_tiet=f"HTTP {e.code}", url=e.url)
        except ContentMismatch as e:
            result.update(song=False, chi_tiet=f"nội dung sai: {e}")
        except Exception as e:  # mất kết nối, timeout, JSON/XML hỏng
            result.update(song=False, chi_tiet=f"{type(e).__name__}: {e}"[:300])
        result["thoi_gian_ms"] = round((time.monotonic() - started) * 1000)
        if not result["song"]:
            report.count("nguon_chet")
            log.warning("[%s] HỎNG — %s", name, result["chi_tiet"])
        else:
            log.info("[%s] sống — %s (%d ms)", name, result["chi_tiet"], result["thoi_gian_ms"])
        results[name] = result
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return report, results


def is_source_alive(name: str) -> bool:
    """Theo lần kiểm gần nhất. Chưa kiểm lần nào → coi như sống (để công đoạn tự thử)."""
    if not HEALTH_FILE.exists():
        return True
    return json.loads(HEALTH_FILE.read_text(encoding="utf-8")).get(name, {}).get("song", True)


def self_check() -> None:
    assert source_name_for_url("https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/1") == "moj_gateway"
    assert source_name_for_url("https://congbaocdn.chinhphu.vn/x.pdf") == "congbao"
    assert source_name_for_url("https://datafiles.chinhphu.vn/cpp/files/vbpq/a.pdf") == "vanban_chinhphu"
    assert source_name_for_url("https://vbpl.vn/sitemap/1.xml") == "vbpl_sitemap"
    assert source_name_for_url("https://example.org/") == "example.org"
    assert set(PROBES) == set(SOURCES), "mỗi nguồn phải có hàm kiểm sống"
    print("PASS")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    report, results = check_sources()
    for result in results.values():
        print(f"{'SỐNG' if result['song'] else 'CHẾT':<5} {result['nguon']:<16} {result['thoi_gian_ms']:>6} ms  {result['chi_tiet']}")
    print(report.summary())


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

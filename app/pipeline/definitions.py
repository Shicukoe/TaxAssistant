"""Pipeline dữ liệu: nối các công đoạn của app/ingest thành một job Dagster.

Chạy (qua scripts/run_pipeline.sh, script này đặt DAGSTER_HOME). Giải thích đầy đủ: docs/pipeline-du-lieu.md.
    bash scripts/run_pipeline.sh        chạy toàn bộ một lần
    bash scripts/run_pipeline.sh ui     giao diện web: lịch sử chạy, log từng công đoạn;
                                        lịch hằng tuần chỉ chạy khi cửa sổ này đang mở

Mỗi công đoạn là một asset. Log của từng công đoạn tách riêng trong giao diện; báo cáo (đếm kết
quả, danh sách văn bản lỗi kèm lý do) hiện ở phần metadata. Công đoạn lỗi thì công đoạn phụ thuộc
nó không chạy; công đoạn độc lập vẫn chạy. Bài kiểm "blocking" không qua cũng chặn công đoạn sau.

File này chỉ nối — mọi logic tải, tách, nạp nằm trong app/ingest.
"""

from collections.abc import Callable

import dagster as dg

from app.ingest import check_document_quality as quality
from app.ingest import check_golden_cases as golden
from app.ingest import check_sources as sources
from app.ingest import discover_from_other_sources as other_sources
from app.ingest import download_from_congbao as congbao
from app.ingest import download_moj_documents as moj
from app.ingest import embed_chunks as embeddings
from app.ingest import link_consolidated_documents as consolidated
from app.ingest import link_replaced_documents as replaced
from app.ingest import read_attachments as attachments
from app.ingest import save_to_database as database
from app.ingest.stage_report import StageReport

# Tỷ lệ lỗi tối đa của mỗi công đoạn trước khi bài kiểm báo trượt.
MAX_FAILURE_SHARE_DOWNLOAD = 0.05
MAX_FAILURE_SHARE_DATABASE = 0.01
# Sitemap lần này phải còn ít nhất bấy nhiêu phần danh sách đã biết, nếu không là sitemap có vấn đề.
MIN_SITEMAP_SHARE_OF_KNOWN = 0.9

# Nguồn sập (SourceUnavailableError, lỗi mạng): thử lại cả công đoạn sau 10 phút, rồi 20 phút.
# Văn bản đã tải ở lần trước được bỏ qua nên chạy lại không tốn gì thêm.
SOURCE_RETRY = dg.RetryPolicy(max_retries=2, delay=600, backoff=dg.Backoff.EXPONENTIAL)


def _failure_share_check(report: StageReport, max_share: float, *, blocking_severity: bool = True) -> dg.AssetCheckResult:
    share = report.failure_share()
    return dg.AssetCheckResult(
        check_name="ty_le_loi",
        passed=share <= max_share,
        severity=dg.AssetCheckSeverity.ERROR if blocking_severity else dg.AssetCheckSeverity.WARN,
        metadata={"ty_le_loi": round(share, 4), "nguong": max_share, "so_loi": report.failure_count},
    )


def _failure_check_spec(asset_name: str, max_share: float, blocking: bool) -> dg.AssetCheckSpec:
    return dg.AssetCheckSpec(
        "ty_le_loi", asset=asset_name, blocking=blocking,
        description=f"Tỷ lệ văn bản lỗi không quá {max_share:.0%}.",
    )


def _materialize(stage: Callable[[], StageReport], checks: Callable[[StageReport], list[dg.AssetCheckResult]]):
    report = stage()
    return dg.MaterializeResult(metadata=report.as_metadata(), check_results=checks(report))


def _require_alive(source_name: str) -> None:
    """source_health báo nguồn chết → dừng ngay với tên nguồn. allow_retries=False: RetryPolicy (10 rồi 20 phút)
    không giúp gì vì source_health không chạy lại giữa chừng — lần chạy sau (tuần sau, hoặc bấm chạy lại) mới kiểm lại."""
    if not sources.is_source_alive(source_name):
        raise dg.Failure(description=f"[{source_name}] source_health báo nguồn chết — xem asset source_health",
                         allow_retries=False)


@dg.asset(
    group_name="nguon",
    description="Kiểm sống từng trang nguồn, kiểm cả NỘI DUNG trả về → data/raw/source_health.json.",
    check_specs=[dg.AssetCheckSpec(f"nguon_{name}", asset="source_health",
                                   description=f"{name}: {source.role}") for name, source in sources.SOURCES.items()],
)
def source_health() -> dg.MaterializeResult:
    report, results = sources.check_sources()
    checks = [
        dg.AssetCheckResult(
            check_name=f"nguon_{name}", passed=result["song"], severity=dg.AssetCheckSeverity.WARN,
            metadata={"chi_tiet": result["chi_tiet"], "thoi_gian_ms": result["thoi_gian_ms"],
                      "kiem_luc": result["kiem_luc"], **({"url": result["url"]} if result.get("url") else {})},
        )
        for name, result in results.items()
    ]
    table = "\n".join(f"{'SỐNG' if r['song'] else 'CHẾT'}  {n} — {r['chi_tiet']}" for n, r in results.items())
    return dg.MaterializeResult(metadata={**report.as_metadata(), "trang_thai_nguon": table}, check_results=checks)


@dg.asset(
    group_name="nguon",
    deps=[source_health],
    description="RSS congbao + docid mới của vanban.chinhphu.vn → văn bản thuế; tải bản gốc văn bản Bộ Tư pháp chưa có. "
                "Không phụ thuộc nhánh Bộ Tư pháp.",
    check_specs=[
        _failure_check_spec("other_source_documents", MAX_FAILURE_SHARE_DOWNLOAD, blocking=False),
        dg.AssetCheckSpec("rss_congbao_co_the_sot", asset="other_source_documents",
                          description="RSS congbao chỉ giữ 50 mục — cả 50 đều mới hơn lần chạy trước thì có thể đã sót."),
    ],
)
def other_source_documents() -> dg.MaterializeResult:
    report, not_on_moj = other_sources.discover_from_other_sources()
    checks = [
        _failure_share_check(report, MAX_FAILURE_SHARE_DOWNLOAD, blocking_severity=False),
        dg.AssetCheckResult(check_name="rss_congbao_co_the_sot", passed=report.counts["rss_congbao_co_the_sot"] == 0,
                            severity=dg.AssetCheckSeverity.WARN),
    ]
    metadata = {**report.as_metadata(), "chua_co_tren_bo_tu_phap": "\n".join(not_on_moj) or "không có"}
    return dg.MaterializeResult(metadata=metadata, check_results=checks)


@dg.asset(
    group_name="bo_tu_phap",
    deps=[source_health],
    retry_policy=SOURCE_RETRY,
    description="Đọc sitemap vbpl.vn → data/raw/moj/sitemap.tsv (chỉ thêm, không xoá).",
    check_specs=[
        dg.AssetCheckSpec("sitemap_day_du", asset="moj_document_list", blocking=True,
                          description="Sitemap lần này còn ít nhất 90% số văn bản đã biết."),
        dg.AssetCheckSpec("doc_duoc_moi_sitemap", asset="moj_document_list",
                          description="Không file sitemap con nào lỗi."),
    ],
)
def moj_document_list() -> dg.MaterializeResult:
    _require_alive("vbpl_sitemap")

    def checks(report: StageReport) -> list[dg.AssetCheckResult]:
        found, known = report.counts["ung_vien_trong_sitemap"], report.counts["tong_trong_danh_sach"]
        return [
            dg.AssetCheckResult(check_name="sitemap_day_du", passed=found >= MIN_SITEMAP_SHARE_OF_KNOWN * known,
                                metadata={"trong_sitemap": found, "da_biet": known}),
            dg.AssetCheckResult(check_name="doc_duoc_moi_sitemap", passed=report.failure_count == 0,
                                severity=dg.AssetCheckSeverity.WARN, metadata={"sitemap_loi": report.failure_count}),
        ]
    return _materialize(moj.update_document_list, checks)


@dg.asset(
    group_name="bo_tu_phap",
    deps=[moj_document_list],
    retry_policy=SOURCE_RETRY,
    description="JSON văn bản mới + tải lại văn bản thuế còn hiệu lực; bản bị cổng sửa → history/.",
    check_specs=[_failure_check_spec("moj_documents", MAX_FAILURE_SHARE_DOWNLOAD, blocking=True)],
)
def moj_documents() -> dg.MaterializeResult:
    _require_alive("moj_gateway")
    return _materialize(moj.download_documents,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DOWNLOAD)])


@dg.asset(
    group_name="bo_tu_phap",
    deps=[moj_documents],
    retry_policy=SOURCE_RETRY,
    description="PDF/DOC của văn bản thuế mà JSON không có chữ.",
    check_specs=[_failure_check_spec("moj_attachments", MAX_FAILURE_SHARE_DOWNLOAD, blocking=False)],
)
def moj_attachments() -> dg.MaterializeResult:
    return _materialize(moj.download_attachments,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DOWNLOAD, blocking_severity=False)])


@dg.asset(
    group_name="congbao",
    deps=[moj_documents, moj_attachments],
    retry_policy=SOURCE_RETRY,
    description="Văn bản còn hiệu lực mà cổng Bộ Tư pháp không có chữ, không có file → tìm trên congbao.",
    check_specs=[_failure_check_spec("congbao_documents", MAX_FAILURE_SHARE_DOWNLOAD, blocking=False)],
)
def congbao_documents() -> dg.MaterializeResult:
    return _materialize(congbao.download_missing_from_congbao,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DOWNLOAD, blocking_severity=False)])


@dg.asset(
    group_name="file_dinh_kem",
    deps=[moj_attachments, congbao_documents, other_source_documents],
    description="Apache Tika đọc .doc/RTF/PDF chưa đọc thành XHTML (cần Java + Tika, xem .env); đếm dòng phải sửa mã TCVN3.",
    check_specs=[_failure_check_spec("converted_attachments", MAX_FAILURE_SHARE_DOWNLOAD, blocking=False)],
)
def converted_attachments() -> dg.MaterializeResult:
    return _materialize(attachments.convert_attachments,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DOWNLOAD, blocking_severity=False)])


@dg.asset(
    group_name="database",
    deps=[moj_documents, converted_attachments],
    description="Nạp văn bản thuế mới hoặc đã đổi vào PostgreSQL (cần .env). JSON rỗng → chữ từ file đính kèm. "
                "Kiểm chất lượng từng văn bản; trượt kiểm nặng → cách ly (tìm được, không trích).",
    check_specs=[
        _failure_check_spec("database_documents", MAX_FAILURE_SHARE_DATABASE, blocking=True),
        dg.AssetCheckSpec("van_ban_cach_ly", asset="database_documents",
                          description="Văn bản đang cách ly chờ xem tay (python -m app.ingest.check_document_quality)."),
        dg.AssetCheckSpec("bo_do_co_dinh", asset="database_documents",
                          description="Mọi ca lỗi đã gặp thật vẫn được xử lý đúng (python -m app.ingest.check_golden_cases)."),
    ],
)
def database_documents() -> dg.MaterializeResult:
    def checks(report: StageReport) -> list[dg.AssetCheckResult]:
        quarantined = quality.quarantine_list()
        failed_cases = [(d, e) for _, d, e in golden.run_cases() if e is not None]
        return [
            _failure_share_check(report, MAX_FAILURE_SHARE_DATABASE),
            dg.AssetCheckResult(
                check_name="bo_do_co_dinh", passed=not failed_cases, severity=dg.AssetCheckSeverity.ERROR,
                metadata={"so_ca_truot": len(failed_cases),
                          "ca_truot": "\n".join(f"{d} → {e}" for d, e in failed_cases) or "không có"},
            ),
            # Luôn cảnh báo khi còn văn bản cách ly — để hàng đợi xem tay luôn hiện trên giao diện.
            dg.AssetCheckResult(
                check_name="van_ban_cach_ly", passed=not quarantined, severity=dg.AssetCheckSeverity.WARN,
                metadata={"so_van_ban": len(quarantined),
                          "danh_sach": "\n".join(f"{u} {s} — {r[:120]}" for u, s, _, r in quarantined[:50]) or "không có"},
            ),
        ]
    return _materialize(database.save_documents_to_database, checks)


@dg.asset(
    group_name="database",
    deps=[database_documents],
    description="Nối văn bản hợp nhất với văn bản gốc (hop_nhat, sua_doi) và kiểm JSON có đúng văn bản không.",
    check_specs=[
        dg.AssetCheckSpec("json_dung_van_ban", asset="consolidated_links",
                          description="Số hiệu ở đầu chữ khớp số hiệu của văn bản; văn bản lệch không bao giờ được dùng làm căn cứ."),
    ],
)
def consolidated_links() -> dg.MaterializeResult:
    def checks(report: StageReport) -> list[dg.AssetCheckResult]:
        # Lỗi trong báo cáo này là văn bản có JSON lệch — liệt kê để người xem tự đối chiếu với bản gốc.
        return [dg.AssetCheckResult(check_name="json_dung_van_ban", passed=report.counts["json_lech_van_ban"] == 0,
                                    severity=dg.AssetCheckSeverity.WARN,
                                    metadata={"so_van_ban_lech": report.counts["json_lech_van_ban"]})]
    return _materialize(consolidated.link_consolidated_documents, checks)


@dg.asset(
    group_name="database",
    deps=[database_documents],
    description="Văn bản bị văn bản mới tuyên bố hết hiệu lực (thay_the) — tìm kiếm xếp sau và ghi rõ nhãn.",
    check_specs=[_failure_check_spec("replaced_links", MAX_FAILURE_SHARE_DATABASE, blocking=False)],
)
def replaced_links() -> dg.MaterializeResult:
    return _materialize(replaced.link_replaced_documents,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DATABASE, blocking_severity=False)])


@dg.asset(
    group_name="database",
    deps=[database_documents],
    description="Vector BGE-M3 cho các đoạn mới hoặc vừa nạp lại (cần server embedding: bash scripts/run_embedding_server.sh).",
    check_specs=[_failure_check_spec("chunk_embeddings", MAX_FAILURE_SHARE_DATABASE, blocking=False)],
)
def chunk_embeddings() -> dg.MaterializeResult:
    return _materialize(embeddings.embed_pending_chunks,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DATABASE, blocking_severity=False)])


# Chạy tuần tự trong một tiến trình: các công đoạn cùng gọi một máy chủ thì không chạy song song,
# giữ đúng nhịp FETCH_DELAY_SECONDS; log cũng dễ đọc hơn.
update_all_data = dg.define_asset_job(
    "cap_nhat_du_lieu",
    selection=dg.AssetSelection.all(),
    executor_def=dg.in_process_executor,
    description="Tải mới, tải lại văn bản còn hiệu lực, tìm bổ sung trên congbao, nạp database.",
)

# Lịch hằng tuần. Chỉ chạy khi Dagster đang mở (run_pipeline.sh ui). Máy tắt lúc tới giờ thì lần mở
# sau chạy bù một lần: với lịch không chia partition, Dagster chỉ xét lần hẹn gần nhất bị lỡ.
weekly_update = dg.ScheduleDefinition(
    name="cap_nhat_hang_tuan",
    job=update_all_data,
    cron_schedule="0 9 * * 1",
    execution_timezone="Asia/Ho_Chi_Minh",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

defs = dg.Definitions(
    assets=[source_health, other_source_documents,
            moj_document_list, moj_documents, moj_attachments, congbao_documents, converted_attachments,
            database_documents, consolidated_links, replaced_links, chunk_embeddings],
    jobs=[update_all_data],
    schedules=[weekly_update],
)

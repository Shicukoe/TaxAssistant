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

from app.ingest import download_from_congbao as congbao
from app.ingest import download_moj_documents as moj
from app.ingest import save_to_database as database
from app.ingest.stage_report import StageReport

# Ngưỡng tạm — chỉnh sau khi xem vài lần chạy thật (giống cách đặt ngưỡng trong docs/danh-gia.md).
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


@dg.asset(
    group_name="bo_tu_phap",
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
    group_name="database",
    deps=[moj_documents],
    description="Nạp văn bản thuế mới hoặc đã đổi vào PostgreSQL (cần .env).",
    check_specs=[_failure_check_spec("database_documents", MAX_FAILURE_SHARE_DATABASE, blocking=True)],
)
def database_documents() -> dg.MaterializeResult:
    return _materialize(database.save_documents_to_database,
                        lambda r: [_failure_share_check(r, MAX_FAILURE_SHARE_DATABASE)])


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
    assets=[moj_document_list, moj_documents, moj_attachments, congbao_documents, database_documents],
    jobs=[update_all_data],
    schedules=[weekly_update],
)

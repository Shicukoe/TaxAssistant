"""Báo cáo của một công đoạn: đếm kết quả và ghi lỗi của từng văn bản.

Một văn bản lỗi chỉ thêm một dòng vào `failures`, không làm dừng công đoạn
(quy tắc bất biến số 11 trong docs/architecture.md). Dagster hiện báo cáo này
trong giao diện; chạy tay bằng `python -m` thì in ra màn hình.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field

# Hiện tối đa bấy nhiêu lỗi trong giao diện — đủ để nhìn ra kiểu lỗi, không làm ngợp.
MAX_FAILURES_SHOWN = 50


@dataclass
class StageReport:
    stage: str
    counts: Counter = field(default_factory=Counter)
    failures: list[tuple[str, str]] = field(default_factory=list)  # (văn bản / file, lý do)

    def count(self, outcome: str, n: int = 1) -> None:
        self.counts[outcome] += n

    def fail(self, item: str, error: BaseException | str, log: logging.Logger) -> None:
        reason = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
        self.failures.append((item, reason[:300]))
        log.warning("LỖI %s — %s", item, reason[:300])

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    def failure_share(self) -> float:
        """Tỷ lệ lỗi trên tổng số mục đã xử lý."""
        total = sum(self.counts.values()) + self.failure_count
        return self.failure_count / total if total else 0.0

    def summary(self) -> str:
        parts = [f"{k} {v}" for k, v in sorted(self.counts.items())] + [f"lỗi {self.failure_count}"]
        return f"{self.stage}: " + ", ".join(parts)

    def as_metadata(self) -> dict:
        """Dạng Dagster hiện được trong giao diện."""
        return {
            **{k: int(v) for k, v in self.counts.items()},
            "loi": self.failure_count,
            "ty_le_loi": round(self.failure_share(), 4),
            "danh_sach_loi": "\n".join(f"{i} — {r}" for i, r in self.failures[:MAX_FAILURES_SHOWN]) or "không có",
        }


def self_check() -> None:
    log = logging.getLogger("self_check")
    log.disabled = True
    report = StageReport("thử")
    report.count("tai_moi", 3)
    report.fail("doc-1", ValueError("JSON hỏng"), log)
    assert report.failure_count == 1
    assert report.failure_share() == 0.25
    assert report.as_metadata()["tai_moi"] == 3
    assert "ValueError: JSON hỏng" in report.as_metadata()["danh_sach_loi"]
    assert report.summary() == "thử: tai_moi 3, lỗi 1"
    print("PASS")


if __name__ == "__main__":
    self_check()

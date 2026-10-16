"""Cấu hình đọc từ .env. Không có giá trị bí mật nào hard-code ở đây."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def require_env(name: str) -> str:
    """Giá trị bắt buộc trong .env — thiếu thì báo lỗi kèm cách sửa."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Thiếu {name} trong .env — copy .env.example thành .env rồi điền.")
    return value


# --- PostgreSQL (tên biến theo chuẩn của Postgres) ---
# Mật khẩu chỉ bắt buộc khi kết nối (xem setup_database.create_database_if_missing) —
# để bộ tải văn bản chạy được mà không cần database.
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PGDATABASE = os.getenv("PGDATABASE", "taxassistant")

# Kết nối tới database quản trị "postgres" — chỉ dùng để tạo database của app lần đầu.
ADMIN_DATABASE_CONNECTION = (
    f"host={PGHOST} port={PGPORT} user={PGUSER} password={PGPASSWORD} dbname=postgres"
)
# Kết nối tới database của app.
DATABASE_CONNECTION = (
    f"host={PGHOST} port={PGPORT} user={PGUSER} password={PGPASSWORD} dbname={PGDATABASE}"
)

# --- Giới hạn chi phí (xem docs/architecture.md, mục Chi phí) ---
BUDGET_MONTHLY_VND = int(os.getenv("BUDGET_MONTHLY_VND", "300000"))
BUDGET_USD_PER_VND = float(os.getenv("BUDGET_USD_PER_VND", "0.0000385"))
QUOTA_QUESTIONS_PER_5H = int(os.getenv("QUOTA_QUESTIONS_PER_5H", "10"))
BUDGET_MONTHLY_USD = BUDGET_MONTHLY_VND * BUDGET_USD_PER_VND

# --- Thu thập dữ liệu (xem docs/nguon-du-lieu.md) ---
# vbpl.vn trả 403 với User-Agent mặc định của curl → cần UA kiểu browser.
FETCH_USER_AGENT = os.getenv("FETCH_USER_AGENT", "Mozilla/5.0")
# Gọi chậm, có nhịp. Tốc độ tối đa các trang cho phép chưa được kiểm chứng.
FETCH_DELAY_SECONDS = float(os.getenv("FETCH_DELAY_SECONDS", "2"))
# Quy tắc: luôn lưu bản gốc ra đĩa trước khi xử lý — nguồn chính có thể tắt bất cứ lúc nào.
RAW_DATA_DIR = PROJECT_ROOT / os.getenv("RAW_DATA_DIR", "./data/raw")

# --- Claude API — chưa cần cho tới bước "Trả lời" ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_FOR_ANSWERS = "claude-opus-5"  # viết câu trả lời — bước người dùng thật sự đọc
MODEL_FOR_CHEAP_STEPS = "claude-haiku-4-5"  # phân loại câu hỏi, lọc kết quả

# Giá USD/1M token — bảng giá đã verify 2026-09-28.
PRICES_USD_PER_MILLION_TOKENS = {
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}

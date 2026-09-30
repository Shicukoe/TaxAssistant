"""Cấu hình đọc từ .env. Không có giá trị bí mật nào hard-code ở đây."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _require(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Thiếu {name} trong .env — copy .env.example thành .env rồi điền.")
    return v


# --- PostgreSQL ---
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = _require("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE", "tro_ly_thue")

# `dbname` trỏ tới DB quản trị, dùng khi cần tạo PGDATABASE lần đầu.
ADMIN_DSN = f"host={PGHOST} port={PGPORT} user={PGUSER} password={PGPASSWORD} dbname=postgres"
DSN = f"host={PGHOST} port={PGPORT} user={PGUSER} password={PGPASSWORD} dbname={PGDATABASE}"

# --- Giới hạn chi phí (xem docs/quyet-dinh.md, mục Chi phí) ---
BUDGET_MONTHLY_VND = int(os.getenv("BUDGET_MONTHLY_VND", "300000"))
# ponytail: tỷ giá là một con số phải tinh chỉnh, không phải hằng số. Tỷ giá thật trôi.
BUDGET_USD_PER_VND = float(os.getenv("BUDGET_USD_PER_VND", "0.0000385"))
QUOTA_QUESTIONS_PER_5H = int(os.getenv("QUOTA_QUESTIONS_PER_5H", "10"))
BUDGET_MONTHLY_USD = BUDGET_MONTHLY_VND * BUDGET_USD_PER_VND

# --- Thu thập dữ liệu (xem docs/nguon-du-lieu.md) ---
# vbpl.vn trả 403 với User-Agent mặc định của curl → cần UA kiểu browser.
FETCH_USER_AGENT = os.getenv("FETCH_USER_AGENT", "Mozilla/5.0")
# Gọi chậm, có nhịp. Tốc độ tối đa các trang cho phép chưa được kiểm chứng.
FETCH_DELAY_SECONDS = float(os.getenv("FETCH_DELAY_SECONDS", "2"))
# Quy tắc: luôn lưu bản gốc ra đĩa trước khi xử lý — nguồn chính có thể tắt bất cứ lúc nào.
RAW_STORE_PATH = ROOT / os.getenv("RAW_STORE_PATH", "./data/raw")

# --- Claude API — chưa cần cho tới bước "Trả lời" ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_ANSWER = "claude-opus-5"
MODEL_CHEAP = "claude-haiku-4-5"

# Giá USD/1M token — bảng giá đã verify 2026-09-28.
PRICES_USD_PER_MTOK = {
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}

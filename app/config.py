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

# --- Thu thập dữ liệu (xem docs/nguon-du-lieu.md) ---
# vbpl.vn trả 403 với User-Agent mặc định của curl → cần UA kiểu browser.
FETCH_USER_AGENT = os.getenv("FETCH_USER_AGENT", "Mozilla/5.0")
# Gọi chậm, có nhịp. Tốc độ tối đa các trang cho phép chưa được kiểm chứng.
FETCH_DELAY_SECONDS = float(os.getenv("FETCH_DELAY_SECONDS", "2"))
# Quy tắc: luôn lưu bản gốc ra đĩa trước khi xử lý — nguồn chính có thể tắt bất cứ lúc nào.
RAW_DATA_DIR = PROJECT_ROOT / os.getenv("RAW_DATA_DIR", "./data/raw")

# --- Model tự host trên laptop (xem docs/architecture.md, mục Model AI) ---
# llama-server nói API kiểu OpenAI; đổi sang vLLM/SGLang trên VPS chỉ đổi địa chỉ này.
# Khởi động server: bash scripts/run_model_server.sh (cổng mặc định của llama-server là 9931).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:9931/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5-4b")  # tên đặt bằng cờ -a của llama-server
# Mọi lời gọi model gửi rõ thông số lấy mẫu — không dựa vào mặc định của server (giá trị trong yêu cầu luôn thắng).
# Lý do và nguồn nghiên cứu: docs/danh-gia.md, mục "Thông số lấy mẫu khi viết câu trả lời".
LLM_ANSWER_TEMPERATURE = float(os.getenv("LLM_ANSWER_TEMPERATURE", "0.4"))  # T=0 làm model nhỏ dễ lặp vô tận
LLM_CLASSIFY_TEMPERATURE = float(os.getenv("LLM_CLASSIFY_TEMPERATURE", "0"))  # đầu ra ngắn, bị schema ép
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.8"))  # theo model card Qwen3.5, chế độ không suy luận
LLM_TOP_K = int(os.getenv("LLM_TOP_K", "20"))
LLM_SEED = int(os.getenv("LLM_SEED", "42"))  # cố định → cùng câu hỏi ra cùng câu trả lời (để debug)
LLM_ANSWER_MAX_TOKENS = int(os.getenv("LLM_ANSWER_MAX_TOKENS", "1500"))  # chặn lặp vô tận
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# Guardrail g: mỗi câu kết luận phải được căn cứ ủng hộ (docs/danh-gia.md). Model NLI đa ngôn ngữ, chạy CPU.
NLI_MODEL = os.getenv("NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
NLI_SUPPORT_THRESHOLD = float(os.getenv("NLI_SUPPORT_THRESHOLD", "0.5"))  # TẠM — đặt lại trên tập kiểm định
# Chế độ đo (shadow): luôn chấm và lưu điểm, nhưng CHƯA hiện cảnh báo cho người dùng tới khi hiệu chỉnh xong ngưỡng.
# Đo 22/10/2026: câu sai đối tượng (rượu của thuyền viên áp cho hành khách) được 0,780 điểm ủng hộ — qua ngưỡng 0,5.
NLI_WARNINGS_VISIBLE = os.getenv("NLI_WARNINGS_VISIBLE", "false").lower() == "true"

# README của langgraph-checkpoint-postgres: đọc lại checkpoint không giới hạn kiểu có thể bị lợi dụng chạy code.
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

# --- Giám khảo cho bộ đo — chỉ dùng khi chạy bộ đo, không bao giờ trong app ---
# Điểm chấm của giám khảo không bao giờ làm dữ liệu huấn luyện (quy tắc bất biến số 13).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-opus-5-5")

# Giá USD/1M token, theo bảng giá trong skill claude-api (bản lưu 2026-10-06) — kiểm lại khi viết bộ đo.
PRICES_USD_PER_MILLION_TOKENS = {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0},
}

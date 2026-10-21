# Quy tắc viết code

## Chung

- **Viết ít nhất có thể.** Trước khi viết: việc này có cần không? Code sẵn trong dự án làm được chưa? Thư viện chuẩn Python làm được chưa? Database (ràng buộc `CHECK`, index) làm được chưa? Chỉ khi cả bốn câu là "không" mới viết mới.
- **Không thêm thư viện** nếu vài dòng code làm được. Thêm thư viện phải được người dùng đồng ý (xem `ai-workflow-rules.md`).
- **Không trừu tượng hóa trước.** Không interface cho một cách cài đặt, không cấu hình cho giá trị không bao giờ đổi, không khung sườn "để sau dùng".
- **Sửa lỗi ở gốc.** Lỗi nằm trong hàm dùng chung thì sửa trong hàm đó, không vá ở từng chỗ gọi.
- **Mỗi logic không tầm thường có đúng một bài tự kiểm chạy được** — hàm `self_check()` dùng `assert`, gọi bằng `python -m app.<module> --check`, không gọi mạng. Không dùng framework test, không fixture.

## Đặt tên

- **Tên file là động từ nói việc nó làm:** `download_moj_documents.py`, `split_articles.py`, `save_to_database.py`, `setup_database.py`. Không đặt theo tên nguồn hay danh từ mơ hồ (`vbpl.py`, `parse.py`, `load.py`).
- **Hàm, biến: tiếng Anh đầy đủ, không viết tắt:** `is_tax_document`, `has_text_content`, `ARTICLE_HEADING`. Không `t`, `cur`, `run`, `ART`.
- **Thuật ngữ luật trong code:** Điều = article, khoản = clause, điểm = point. Giá trị lưu trong DB giữ như schema: `'dieu'`, `'khoan'`, `'diem'`.
- **Điểm vào là `main()`**, bài tự kiểm là `self_check()` sau cờ `--check`.

## Python

- Python 3.12. Ghi kiểu dữ liệu ở chữ ký hàm, dùng cú pháp mới (`str | None`, `list[str]`).
- Dữ liệu có cấu trúc dùng `@dataclass`, không dùng dict tự do giữa các hàm.
- Đường dẫn dùng `pathlib.Path`, không ghép chuỗi.
- Mọi cấu hình lấy từ `app/config.py`. Không gọi `os.getenv` ở chỗ khác. Biến bắt buộc dùng `config.require_env(...)` để báo lỗi kèm cách sửa.
- Dòng tối đa 100 ký tự (`[tool.ruff]` trong `pyproject.toml`).
- Chú thích và docstring viết **tiếng Việt**, giải thích *vì sao*, không lặp lại code. Module mở đầu bằng docstring nói nó làm gì và cách chạy.
- Chạy trên Windows console: đặt `PYTHONIOENCODING=utf-8` khi in tiếng Việt.

## Database

- **psycopg 3, SQL viết tay.** Giá trị luôn truyền bằng tham số `%s`, không bao giờ ghép chuỗi. Tên bảng/database cần động thì dùng `psycopg.sql.Identifier`.
- **Migration chỉ đi tiến:** file mới `app/db/migrations/NNN_<việc làm>.sql` (ví dụ `002_add_amendment_index.sql`). **Không sửa file migration đã chạy** — muốn đổi thì thêm file mới.
- **Ràng buộc đặt ở database** (`CHECK`, `NOT NULL`, khóa ngoại) thay vì kiểm trong Python. Mỗi ràng buộc mới có một dòng trong `check_database.py` chứng minh nó chặn dữ liệu sai.
- **Một văn bản = một transaction.** Lỗi giữa chừng thì không để lại văn bản nửa vời.
- Kết nối bằng `config.DATABASE_CONNECTION` (user `taxassistant`).

## Thu thập dữ liệu

- Mọi lần tải đi qua `download_and_save` trong `download_moj_documents.py`: nghỉ `FETCH_DELAY_SECONDS` giữa các lần gọi, dùng `FETCH_USER_AGENT`.
- **Ghi file nguyên tử:** ghi ra `.tmp` rồi đổi tên — bị ngắt giữa chừng không để lại file hỏng.
- **Chạy lại được bất cứ lúc nào:** thứ đã có trên đĩa thì bỏ qua — trừ văn bản còn hiệu lực: tải lại, so dấu vân tay (`document_fingerprint`), khác thì bản cũ vào `history/`. Không bao giờ ghi đè bản gốc.
- **Lỗi mạng tạm thời tự thử lại** trong `http_request` (lỗi mạng, 429, 5xx; chờ 5 rồi 15 giây). Lỗi 4xx khác là lỗi thật, không thử lại.
- File máy chủ báo không có (404) ghi vào `missing.txt` **của nguồn đó** và không thử lại.
- **Cô lập lỗi:** mỗi văn bản tự bắt lỗi, ghi vào `StageReport` (id + lý do), công đoạn chạy tiếp. Chỉ khi lỗi liên tiếp `MAX_CONSECUTIVE_FAILURES` lần mới dừng, bằng `SourceUnavailableError`. Không dùng `sys.exit` trong hàm của công đoạn.
- **Mỗi công đoạn là một hàm trả về `StageReport`** (`update_document_list`, `download_documents`, …). `main()` chỉ gọi hàm đó; Dagster cũng gọi đúng hàm đó.
- **Log bằng `logging.getLogger(__name__)`**, không `print` trong code của công đoạn. Logger tên `app.…` được Dagster thu riêng cho từng công đoạn (`dagster_home/dagster.yaml`).
- **Dữ liệu từ ngoài là không tin được:** ID văn bản phải khớp mẫu (`VALID_DOCUMENT_ID`), tên file đính kèm không được chứa ký tự đường dẫn (`safe_attachment_names`), link tải chỉ chấp nhận http/https của tên miền đã biết — trước khi dùng làm đường dẫn trên đĩa hay gọi mạng.
- Chữ tiếng Việt chuẩn hóa NFC trước khi so khớp.

## Web và API (chưa có — bước Trả lời và Giao diện)

- FastAPI + template Jinja2 render từ server; JS thuần chỉ khi cần tương tác trên trình duyệt. Không bước build.
- Route chỉ nhận yêu cầu, kiểm đầu vào, gọi xuống tầng tìm kiếm/trả lời, rồi render. Không gọi model hay viết SQL trong route.
- **Luồng trả lời bằng LangGraph:** mỗi bước là một node — hàm **async** nhận state (TypedDict) và trả dict chứa phần cập nhật (đúng chữ ký trong mã nguồn `StateGraph`). Async vì `TimeoutPolicy` dựa vào huỷ asyncio; node đồng bộ bị chặn thì timeout không chạy.
- Node không ghi database giữa chừng; chỉ node cuối ghi `questions`/`answers`. Lý do: `interrupt` và thử lại chạy lại node từ đầu — tác dụng phụ trước đó sẽ bị lặp.
- State chỉ chứa thứ cần cho các bước sau (ô hiểu câu hỏi, id các đoạn tìm được, bản nháp, kết quả guardrail) — không nhét cả văn bản luật vào state.
- `RetryPolicy` chỉ cho lỗi kết nối (`llama-server`, Postgres), không thử lại khi model trả lời kém.
- Chi tiết bổ sung khi bắt đầu bước Trả lời.

## Tài liệu

- Tiếng Việt đơn giản, câu ngắn, đọc một lần hiểu ngay.
- Không dùng mã kiểu M1, DEC-049, ADR-0003. Gọi tên sự vật: "bước Tìm kiếm", "quy tắc trích dẫn".
- Quyết định ghi kèm ngày chốt: "(chốt 02/10/2026)".
- Điều chưa kiểm chứng ghi rõ **chưa kiểm**. Số liệu đo được ghi kèm ngày đo.

## Tổ chức file

- `app/config.py` — cấu hình duy nhất
- `app/db/` — schema, migration, tạo user, bài tự kiểm database
- `app/ingest/` — tải, tách, nạp văn bản; mỗi file một việc, tên là việc đó
- `app/pipeline/definitions.py` — nối công đoạn thành pipeline Dagster; không chứa logic
- `scripts/run_model_server.sh` — chạy `llama-server`; mỗi cờ có chú thích lý do, lấy từ README của đúng bản llama.cpp đang dùng
- `scripts/run_pipeline.sh` — chạy pipeline / mở giao diện Dagster. Script viết bằng bash (chạy trên Git Bash và Linux), không viết PowerShell
- `data/raw/` — bản gốc tải về, không commit
- `docs/` — tài liệu; `CLAUDE.md` ở gốc là điểm vào

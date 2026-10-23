# Kiến trúc

Cập nhật: 23/10/2026. Muốn đổi một lựa chọn ở đây thì sửa file này trước, rồi mới sửa code.

## Công nghệ

| Lớp | Chọn | Vai trò / vì sao |
|---|---|---|
| Ngôn ngữ | **Python 3.12** | Một ngôn ngữ cho pipeline, luồng trả lời và web |
| Web | **FastAPI** + **uvicorn**, HTML/CSS/JS thuần render từ server (**Jinja2**) | Không bước build, không framework frontend; độ chặt của trích dẫn nằm ở backend |
| Database | **PostgreSQL 18**, `unaccent` | Chữ, vị trí trích dẫn, quan hệ văn bản, lịch sử hỏi đáp ở một chỗ |
| Truy cập database | **psycopg 3**, SQL viết tay | Không ORM — schema nhỏ, một người viết |
| Tìm kiếm | **Kết hợp** tìm theo từ khóa (full-text, bỏ dấu bằng `unaccent`) + tìm theo nghĩa (vector), gộp bằng reciprocal rank fusion | Mỗi cách bắt được những câu cách kia bỏ sót |
| Lưu vector | **pgvector** trong Postgres | Một câu SQL làm được cả lọc hiệu lực lẫn tìm |
| Embedding | **BGE-M3** (BAAI, MIT, 1.024 chiều, 8.192 token), chạy bằng **`llama-server` thứ hai** (`--embedding --pooling cls`, cổng 9932) trên GPU; GGUF tự chuyển từ trọng số gốc bằng `convert_hf_to_gguf.py` của llama.cpp b11796 | Chạy trên máy. Mỗi đoạn được gắn ngữ cảnh văn bản trước khi tính vector (loại, số hiệu, tên văn bản, tên Điều) — lấy từ database, không cần model |
| Đọc file đính kèm | **Apache Tika 4.1.0** chạy hàng loạt (Tika Pipes) trên **Java Temurin 21** | Một công cụ cho `.doc` Word 97, RTF, PDF. Đầu ra XHTML → bỏ header/footer trang → bộ tách dòng HTML → bộ sửa mã TCVN3 của dự án. Chữ từ PDF đánh dấu OCR (chỉ để tìm, không trích). Java và Tika ở `D:/tools/`, đường dẫn trong `config.py` |
| Model viết | **Qwen3.5-4B** GGUF `Q4_K_M` (2,74 GB), tự host trên laptop — viết câu trả lời, tách câu nhiều ý, phân loại câu hỏi khi từ khoá không ra. Mốc thời gian lấy bằng quy tắc, không dùng model | Câu hỏi không ra khỏi máy; vừa GPU 6 GB cùng model embedding |
| Chạy model | **llama.cpp `llama-server`** b11796, bản dựng Windows CUDA 12.4 | API kiểu OpenAI, ép đầu ra theo JSON schema; mọi tham số là cờ lệnh rõ ràng. File model ở ổ D |
| Kiểm câu trả lời có căn cứ ủng hộ | Cách làm của **AlignScore** với model NLI `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, **ONNX Runtime** float32 trên CPU (`onnxruntime` + `tokenizers`). Bản ONNX chuyển một lần bằng `scripts/convert_nli_to_onnx.sh` ở môi trường riêng; file ở `D:/models/nli-onnx/` | Bắt "suy luận sai": trích đúng chữ nhưng áp sai đối tượng. Chi tiết: `danh-gia.md` guardrail g |
| Cấu hình | **python-dotenv**, file `.env` | Bí mật không nằm trong code |
| Điều phối luồng trả lời | **LangGraph**: `StateGraph`, checkpointer Postgres (`langgraph-checkpoint-postgres`), `stream_mode` gửi tiến độ và từng token lên giao diện, `RetryPolicy` cho lỗi kết nối, timeout từng bước | Lưu trạng thái hội thoại nhiều lượt, xem state sau từng bước |
| Điều phối pipeline | **Dagster** | Mỗi công đoạn là một asset: log riêng, công đoạn lỗi không chặn bước độc lập, kiểm chất lượng dữ liệu (asset check), giao diện xem lịch sử chạy |
| Gọi HTTP | **httpx** | Gọi `llama-server` (model viết, embedding) |
| Truy cập từ xa | **Tailscale** `serve`: web (`127.0.0.1:8000`) vào mạng riêng qua **HTTPS** `https://<tên-máy>.<tailnet>.ts.net` | Không mở gì ra internet; HTTPS cần cho cookie đăng nhập `Secure` |
| Đăng nhập | Email + mật khẩu băm **Argon2id** (**`argon2-cffi`**, thông số mặc định: RFC 9106 low-memory, t=3, 64 MiB, p=4). Đăng ký và quên mật khẩu xác nhận bằng **mã OTP 6 số qua email**, gửi bằng `smtplib` qua **Gmail SMTP + App Password** | Theo OWASP Password Storage, Session Management, Forgot Password, CSRF Prevention cheat sheet |

## Ranh giới thư mục

- `app/config.py` — đọc `.env`, chứa mọi hằng số cấu hình (kết nối DB, địa chỉ `llama-server`, tốc độ tải, tên model). Nơi duy nhất đọc biến môi trường.
- `app/db/` — schema và công cụ database: `create_app_user.sql` (chạy một lần bằng tài khoản quản trị), `setup_database.py` (tạo database, chạy migration), `check_database.py` (bài tự kiểm), `migrations/` (file `.sql` đánh số, chỉ đi tiến).
- `app/ingest/` — lấy văn bản về và đưa vào database. Chỉ ghi các bảng văn bản (`documents`, `provisions`, `chunks`, `chunk_positions`, sau này `amendments`, `embeddings`). Không gọi model AI.
  - `download_moj_documents.py` — sitemap vbpl.vn → JSON cổng Bộ Tư pháp + file đính kèm → `data/raw/moj/`
  - `download_from_congbao.py` — nguồn dự phòng cho văn bản cổng Bộ Tư pháp không có → `data/raw/congbao/`
  - `split_articles.py` — HTML → Điều / khoản / điểm kèm vị trí ký tự (văn bản không có Điều → mục / đoạn). Không đọc mạng, không ghi DB
  - `check_document_quality.py` — phép kiểm bất biến cho từng văn bản (mã chữ, thứ tự đề mục, độ phủ, đoạn quá dài) → `document_checks`; hàng đợi xem tay và lệnh ghi kết quả xem tay → `document_reviews`
  - `check_golden_cases.py` — bộ đo cố định: mỗi lỗi gặp thật là một ca trên văn bản thật
  - `embed_chunks.py` — vector BGE-M3 cho đoạn chưa có vector, gắn ngữ cảnh văn bản (loại, số hiệu, tên văn bản, tên Điều) trước khi tính → bảng `embeddings`. Gọi model embedding qua `app/answer/call_local_model.py` — ngoại lệ duy nhất của "ingest không gọi model"
  - `read_attachments.py` — chữ của file đính kèm: Tika đọc `.doc`/RTF/PDF → XHTML ở `data/converted/` → các dòng chữ (bỏ header/footer trang), sửa mã TCVN3 còn sót; chữ PDF coi là OCR
  - `save_to_database.py` — bản lưu trên đĩa → database
  - `stage_report.py` — báo cáo của một công đoạn: đếm kết quả, danh sách lỗi từng văn bản
  - `check_sources.py` — bảng nguồn (tên, vai trò, ghi nguồn) + kiểm sống từng trang **kèm kiểm nội dung** → `data/raw/source_health.json`; tên nguồn theo địa chỉ cho log lỗi
  - `discover_from_other_sources.py` — RSS congbao + docid mới của vanban.chinhphu.vn → văn bản thuế → đối chiếu Bộ Tư pháp → tải bản gốc văn bản Bộ Tư pháp chưa có
  - `link_consolidated_documents.py` — đọc đoạn mở đầu (hoặc tiêu đề) của văn bản hợp nhất → quan hệ `hop_nhat` (bản hợp nhất → văn bản gốc) và `sua_doi` (văn bản sửa → văn bản gốc); kiểm "JSON có đúng văn bản không" → `documents.content_matches_number`
  - `link_replaced_documents.py` — đọc câu "… số 38/2019/QH14 … hết hiệu lực kể từ …" trong Điều hiệu lực của văn bản mới → quan hệ `thay_the` (văn bản mới → văn bản cũ) kèm ngày, khoản ghi câu đó, có "trừ …" không; view `document_replacements` (migration 009) suy ra cả bản hợp nhất của văn bản cũ
- `app/pipeline/` — nối các công đoạn của `app/ingest/` thành pipeline Dagster (`definitions.py`). Chỉ gọi hàm có sẵn, không chứa logic tải hay tách văn bản.
- `dagster_home/` — nơi Dagster lưu lịch sử chạy và log (không commit, trừ `dagster.yaml`).
- `scripts/run_pipeline.sh` — chạy pipeline một lần, hoặc mở Dagster (`ui`): giao diện web + bộ hẹn giờ chạy hằng tuần. Bash: Git Bash trên Windows, Linux trên VPS. Giải thích Dagster và cách xem lỗi: `pipeline-du-lieu.md`.
- `data/raw/` — bản gốc tải về (không commit). Mỗi nguồn một thư mục: `moj/`, `congbao/` (bù cho văn bản Bộ Tư pháp thiếu chữ, theo mã Bộ Tư pháp), `congbao/new/` (văn bản mới phát hiện qua RSS, theo mã congbao), `vanban_chinhphu/` (theo docid). `source_health.json` — kết quả kiểm sống gần nhất. `data/converted/` — XHTML Tika đọc từ file đính kèm, `<đường dẫn gốc>.xml` (không commit, tạo lại được từ bản gốc). Chỉ thêm, không sửa: bản bị cổng sửa thì bản cũ chuyển vào `data/raw/moj/history/{id}/{ngày}.json`.
- `docs/` — tài liệu thiết kế.

- `app/answer/` — luồng trả lời (LangGraph). **Bản demo** từ 22/10/2026; từ 23/10/2026 đã có tìm kết hợp và kéo Điều được dẫn chiếu, chưa có reranker, lịch sử sửa đổi theo từng Điều.
  - `call_local_model.py` — **chỗ duy nhất gọi model**: model viết (`llama-server` cổng 9931, trả token và thời gian chạy) và model embedding BGE-M3 (cổng 9932)
  - `split_question.py` — câu hỏi nhiều ý → 2–5 câu tìm kiếm ngắn (model, JSON schema); câu ngắn một ý thì không tách, không gọi model
  - `understand_question.py` — mốc thời gian (quy tắc), loại thuế và loại câu hỏi (quy tắc từ khoá + model, T=0), mang ô từ lượt trước sang
  - `search_articles.py` — tìm kết hợp: từ khoá (full-text) + theo nghĩa (BGE-M3, pgvector), gộp bằng RRF (k = 60), cùng một bộ lọc hiệu lực tại mốc; server embedding tắt → chỉ từ khoá, báo ở debug
  - `add_referenced_articles.py` — kéo thêm Điều mà các Điều tìm được dẫn chiếu tới **trong cùng văn bản** ("theo quy định tại khoản 2 Điều 9 Luật này"), bằng quy tắc, không gọi model
  - `add_deadline_rule.py` — câu hỏi về thời hạn: thêm Điều quy tắc ngày nghỉ, tính sẵn lịch (thứ Bảy, Chủ nhật, lễ dương lịch) cho ngày "D tháng M" trong các đoạn tìm được; sau khi kiểm trích dẫn, thêm dòng lịch vào kết luận
  - `answer_simple_questions.py` — hai nhánh không gọi model: chào hỏi (câu mẫu), khái niệm (tra định nghĩa trong luật)
  - `measure_search.py` + `search_eval_questions.json` — đo recall@5, MRR@10 cho từ khoá / theo nghĩa / kết hợp; bộ câu hỏi hiện là **bộ tạm**
  - `write_answer.py` — model viết câu trả lời theo JSON schema (kết luận + căn cứ trích nguyên văn)
  - `check_citations.py` — guardrail tất định: trích dẫn khớp từng chữ, chữ OCR không trích, con số có căn cứ
  - `check_claim_support.py` — guardrail g: mỗi câu kết luận có được khoản chứa trích dẫn ủng hộ không (cách AlignScore, model NLI đa ngôn ngữ chạy CPU bằng ONNX Runtime)
  - `answer_graph.py` — nối các bước bằng LangGraph + checkpointer Postgres; bước cuối ghi `questions`, `answers`, `usage_log`
  - `chat_in_terminal.py` — demo: chat trong terminal, in state sau từng bước để debug
- `scripts/chat_demo.sh` — chạy demo chat (cần `run_model_server.sh` đang chạy)
- `scripts/run_embedding_server.sh` — llama-server thứ hai cho BGE-M3 (cổng 9932)
- `scripts/convert_nli_to_onnx.sh` — chuyển model NLI của guardrail g sang ONNX float32 (một lần, môi trường riêng có optimum)

Dự kiến, **chưa có** (đặt tên khi tới bước tương ứng):

- thư mục tìm kiếm đầy đủ (bước Tìm kiếm) — thay `search_articles.py`: tìm kết hợp, embedding, reranker
- web app (bước Giao diện)
- `app/web/` — web app FastAPI + template Jinja2 (bản demo cho mạng nhà từ 22/10/2026); không gọi model hay viết SQL trong route. Hai chế độ trên cùng dữ liệu (chốt 22/10/2026): **Hỏi** (chạy luồng LangGraph của `app/answer`, gửi tiến độ từng bước về trình duyệt) và **Tra cứu** (đọc thẳng văn bản dựng thành HTML từ database — không chuẩn hoá thành PDF; kèm link tải bản gốc). Trích dẫn trong câu trả lời là link tới đúng Điều ở trang tra cứu
  - `server.py` — ứng dụng FastAPI, route, chạy uvicorn trên `127.0.0.1:8000` (vào từ máy khác qua `tailscale serve`). Middleware chặn mặc định: mọi đường dẫn cần phiên đăng nhập trừ trang đăng nhập / đăng ký / quên mật khẩu và `/static`; mọi POST qua kiểm CSRF
  - `authenticate_users.py` — tài khoản, mật khẩu (Argon2id), phiên đăng nhập, khoá tạm khi nhập sai, mã CSRF
  - `send_email_codes.py` — mã OTP: sinh, lưu bản HMAC, giới hạn số lần gửi / nhập, kiểm; gửi email qua SMTP
  - `manage_conversations.py` — ghi cuộc hội thoại theo người (nhận chủ, ẩn khỏi danh sách) và đánh giá câu trả lời
  - `manage_users.py` — lệnh trên laptop: danh sách tài khoản, quyền quản trị, cho phép dùng để huấn luyện, khoá tài khoản, nhận hội thoại cũ chưa có chủ
  - `read_performance.py` — số liệu trang Hiệu năng: số câu đã hỏi, thời gian trả lời (`answers.duration_ms`, migration 010), bộ nhớ GPU (`nvidia-smi`), tốc độ đọc/sinh của model (`/metrics` của `llama-server`)
  - `read_library.py` — câu SQL cho trang tra cứu (danh sách, một văn bản, nhãn)
  - `templates/`, `static/` — HTML, CSS, JS thuần

## Lưu trữ

- **PostgreSQL** (database `taxassistant`): 10 bảng, mỗi bảng có chú thích lý do trong `app/db/migrations/001_create_tables.sql`.
  - `documents` — một văn bản: số hiệu, loại, ngày, hiệu lực, nguồn, link gốc, `text_origin` (`native` / `ocr` / `none`)
  - `document_relations` — văn bản này sửa / thay thế / hướng dẫn văn bản kia. Từ 22/10/2026 có `hop_nhat` và `sua_doi` đọc từ văn bản hợp nhất (`evidence` = `vbhn_preamble` / `vbhn_title`)
  - `documents.content_matches_number` (migration 004) — số hiệu ở đầu chữ văn bản có khớp số hiệu của văn bản không: `false` = JSON chứa văn bản khác (ví dụ NĐ 125/2020 chứa công văn đính chính) → **không bao giờ dùng làm căn cứ**; `null` = đầu văn bản không ghi số, không kiểm được
  - `provisions` — từng Điều / khoản / điểm
  - `chunks` — đoạn dùng để tìm kiếm: một Điều trọn vẹn
  - `chunk_positions` — vị trí ký tự của từng khoản/điểm trong đoạn → dùng để kiểm trích dẫn
  - `amendments` — lịch sử sửa đổi lấy từ chú thích văn bản hợp nhất, tới mức cụm từ
  - `embeddings` — vector của từng đoạn
  - `questions`, `answers` — lịch sử hỏi đáp, **bản ghi chính thức** (lịch sử của mẹ, bộ đo, trang hiệu năng chỉ đọc ở đây). `questions` sẽ có `thread_id` nối sang checkpoint (migration khi viết bước Trả lời)
  - bảng checkpoint của LangGraph (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, do `.setup()` tạo) — **trạng thái lúc chạy**, gồm cả bản nháp trước guardrail. Không hiển thị câu trả lời từ đây. Giá trị đơn giản (mốc thời gian, loại thuế) đọc được bằng JSONB; list/dict nằm ở `checkpoint_blobs` (msgpack), đọc bằng `get_state_history`
  - `usage_log` — token, thời gian chạy (`duration_ms`, migration 003) của từng lần gọi model (cột `cost_usd` có sẵn từ migration 003, luôn 0 với model trên máy)
  - **Tài khoản và dữ liệu huấn luyện** (migration 011, chốt 23/10/2026):
    - `users` — email (chữ thường, duy nhất), tên hiển thị, bản băm Argon2id, `is_admin` (thấy khung debug), `allow_training` (câu hỏi của người này được dùng để fine-tune / đánh giá; mặc định tắt, bật bằng `manage_users.py`), `disabled_at`
    - `sessions` — **chỉ lưu SHA-256 của mã phiên**, mã CSRF, lần dùng cuối, hết hạn tuyệt đối
    - `email_codes` — mã OTP: chỉ lưu HMAC-SHA256 (khoá `AUTH_SECRET` trong `.env`), mục đích (`dang_ky` / `dat_lai_mat_khau`), hết hạn, số lần nhập sai, đã dùng
    - `login_attempts` — mỗi lần đăng nhập (email, đúng / sai) → khoá tạm khi sai nhiều
    - `conversations` — `thread_id` → chủ sở hữu (`user_id`; trống = hội thoại từ terminal hoặc từ trước khi có tài khoản, không hiện trên web), `hidden_at` (nút xoá chỉ ẩn, dữ liệu giữ). `questions.thread_id` có khoá ngoại sang đây
    - `model_calls` — **đúng thứ model đã nhận và trả** cho mỗi lời gọi: request gửi `llama-server` (messages, thông số lấy mẫu, JSON schema) và chữ model trả về. Nguyên liệu fine-tune; prompt nằm trong request nên không cần số phiên bản prompt riêng
    - `answer_feedback` — người hỏi chấm từng câu trả lời: `dung` / `sai` / `chua_du` (ba nhãn của Magesh, `danh-gia.md`) + ghi chú
- **Đĩa** (`data/raw/`, không commit): JSON gốc của cổng Bộ Tư pháp, file PDF/DOC/RTF đính kèm, file tải từ congbao. Database có thể dựng lại hoàn toàn từ đây.
  - Cổng Bộ Tư pháp **có sửa văn bản sau khi đăng**: đo 15/10/2026, 4/20 văn bản còn hiệu lực đổi nội dung sau 13 ngày. Vì vậy mỗi lần chạy tải lại văn bản còn hiệu lực; khác thì giữ bản cũ trong `history/`.
  - Mỗi dòng `documents` ghi `raw_sha256` (bản gốc nào) và `parser_version` (bộ tách nào) → chỉ nạp lại văn bản thật sự thay đổi, và truy được dữ liệu sinh từ đâu.
- **Dagster** (`dagster_home/`): lịch sử chạy, log từng công đoạn, kết quả kiểm chất lượng.
- **Không lưu ở đâu khác.** Không cloud storage, không cache riêng.

### Dữ liệu luật

**Lập trường.** Chỉ lấy dữ liệu công khai và không vi phạm quy định nào đã công bố. Không xin phép, không chờ giấy phép — nghiên cứu cho thấy lĩnh vực này không có nguồn nào cấp phép rõ ràng (chi tiết ở `nguon-du-lieu.md`).

**Nguồn dùng.**
- Cổng dữ liệu JSON của Bộ Tư pháp — nguồn chính cho văn bản luật: đủ nội dung, có trạng thái hiệu lực.
- congbao.chinhphu.vn — nguồn dự phòng.
- gdt.gov.vn — công văn của Cục Thuế trung ương.

**Không dùng.**
- thuvienphapluat.vn, luatvietnam.vn — điều khoản của họ cấm thu thập tự động. Mua tài khoản VIP cũng không được, vì chính thỏa thuận thành viên là thứ cấm.
- Các bộ dữ liệu có sẵn trên mạng — tự xây từ đầu.

**Công văn.** Lấy toàn bộ công văn trung ương lấy được, kể cả bản scan (qua OCR, chỉ để tìm). Công văn quá cũ không có file đính kèm — chấp nhận không có.

**Ba lớp văn bản:** văn bản hợp nhất (để đọc, và chú thích cuối trang cho biết điều nào bị sửa khi nào), văn bản gốc, văn bản sửa đổi.

**Cắt văn bản theo Điều.** Mỗi đoạn tìm kiếm là một Điều trọn vẹn, kèm vị trí từng khoản/điểm để trích dẫn chi tiết. Lý do: cắt nhỏ tới điểm thì nhiều điểm đứng một mình vô nghĩa — điểm a khoản 4 Điều 13 Nghị định 125/2020 chỉ nói "nộp hồ sơ trễ 61–90 ngày", mức phạt 8–15 triệu nằm ở câu dẫn của khoản.
Văn bản không có Điều (thông tư cũ chia theo Phần / Mục / I. / 1.) thì **cắt theo đề mục lớn nhất**, trích dẫn kiểu "mục II.3 Thông tư …". Không có cả đề mục thì cắt theo độ dài. (chốt 02/10/2026)
Cách làm (22/10/2026, đo trên 425 văn bản còn dùng không có Điều):
- Có mục La Mã (I., II. — 204 văn bản) → mỗi **mục La Mã** là một đoạn tìm kiếm; "1." trong mục là khoản, "a)" là điểm. Phần chữ phía trên ("A. VỀ THUẾ MÔN BÀI", "Phần B", "PHẦN Đ" — thứ tự chữ cái tiếng Việt, có khi bỏ chữ; mỗi phần đánh mục lại từ I) **không** làm đoạn — đo được đoạn theo phần to gấp ~3 lần (p90 14.900 ký tự so với 5.800) — mà ghi vào số hiệu mục: `B.II` = "mục II phần B".
- Không có mục La Mã nhưng có "1.", "2." (132 văn bản) → mỗi số là một mục; "a)" là điểm.
- Không có đề mục (89 văn bản, phần lớn là Lệnh công bố, thông tư ngắn) → cắt theo độ dài tại ranh giới dòng, mỗi đoạn ≤ 6.000 ký tự, cấp `doan`.
- Đề mục chỉ được nhận khi **đúng thứ tự** (II sau I, B sau A), như khoản/điểm — dòng "V. Đô thị loại V" trong bảng không mở mục giả. Cấp lưu ở `provisions.level` / `chunk_positions.level`: thêm `muc`, `doan` (migration 005).

**Văn bản chỉ có file đính kèm** (22% văn bản trên cổng JSON) → tải file về lưu bản gốc. (chốt 02/10/2026)

**Mọi chữ lấy từ PDF đều coi là OCR** — chỉ để tìm, không trích. Nhiều PDF là bản scan đã OCR sẵn, chữ sai kiểu "QUYÉT ĐỊNH", và không có cách chắc chắn biết PDF nào là chữ gốc. Chỉ chữ từ HTML của cổng và từ file DOC/RTF mới được trích nguyên văn. (chốt 02/10/2026)

**Bốn lớp giữ dữ liệu sạch** (chốt 22/10/2026). Lý do: sửa từng ca bằng quy tắc riêng không mở rộng được — lỗi kiểu mới chỉ lộ ra khi tình cờ thấy.
1. **Định dạng file do công cụ chuẩn đọc**, không tự viết bộ đọc: **Apache Tika** (chốt 22/10/2026). Apache Tika (Word 97 qua Apache POI, RTF, PDF qua PDFBox) **đã đo trên chính 317 + 141 file** (22/10/2026, `danh-gia.md` mục 2); chạy được trên Linux. Java Temurin 21 và Tika 4.1.0 để ở `D:/tools/` (không thuộc repo).
2. **Kiểm bất biến chung cho từng văn bản, không nhận dạng từng ca.** Mỗi văn bản có một bảng kết quả kiểm (đạt / trượt + lý do): số mục, khoản liên tục; không còn ký tự đặc trưng TCVN3; số hiệu ở đầu chữ khớp số hiệu; đoạn không quá dài; độ phủ chữ; hiệu lực đáng tin. Văn bản trượt phép kiểm nặng bị **cách ly**: vẫn tìm được, không được trích, nằm trong danh sách chờ xem tay (Dagster, sau này cả trang tra cứu). Lỗi kiểu mới vì vậy bị chặn dù chưa ai viết quy tắc cho nó. **Ngoại lệ (người dùng chốt 23/10/2026):** văn bản hợp nhất trượt phép kiểm thứ tự đề mục chỉ bị **cảnh báo**, không cách ly — văn bản hợp nhất rất quan trọng, và số Điều nhảy thường là bình thường (Điều bị bãi bỏ được bỏ khỏi bản hợp nhất, Điều chèn thêm "12a"); lỗi mã chữ vẫn cách ly.
3. **Mỗi lỗi gặp thật thành một ca trong bộ đo cố định** (văn bản thật + kết quả đúng). Sửa bộ tách, bộ đọc nào cũng chạy lại cả bộ — sửa ca mới không được làm hỏng ca cũ.
4. **Học cấu trúc từ nhãn có sẵn thay vì thêm regex:** markup `prov-*` của cổng Bộ Tư pháp làm nhãn cho một bộ phân loại từng dòng (đề mục / khoản / điểm / chữ thường), đo trên văn bản để riêng. Chỉ thay regex khi tốt hơn trên bộ đo; regex còn lại làm đường dự phòng. **Đã đo 22/10/2026: model từng dòng kém regex ở mọi nhãn (F1 trung bình 0,961 so với 0,982) → giữ regex**; thử lại với model có ngữ cảnh khi có lỗi cấu trúc regex không sửa được. Model nào dùng cho việc này phải qua quy tắc bất biến số 10.

**Hiệu lực ghi trên cổng không đáng tin ở văn bản cũ** (đo 22/10/2026: NĐ 24/2007/NĐ-CP về TNDN đã bị thay vẫn ghi "còn hiệu lực"). Văn bản cổng ghi còn hiệu lực (`CHL`, `HHL1P`, trống) mà **không có ngày hết hiệu lực** và **ban hành trước mốc hỏi hơn 10 năm** → nhãn **"cần kiểm hiệu lực"**, khi tìm kiếm xếp sau mọi văn bản không mang nhãn (chốt 22/10/2026; ngưỡng 10 năm là tạm — đo bằng cách xem tay mẫu văn bản bị gắn nhãn). Văn bản hợp nhất không áp quy tắc này (mang ngày ban hành mới). Không tự suy "hết hiệu lực" — chỉ cảnh báo; suy từ quan hệ thay thế làm ở bước Lịch sử sửa đổi.

**Cập nhật** hằng tuần, tự động bằng lịch của Dagster (`cap_nhat_hang_tuan` trong `app/pipeline/definitions.py`, thứ Hai 9:00 giờ Việt Nam). Lịch chỉ chạy khi Dagster đang mở (`run_pipeline.sh ui`). Máy tắt lúc tới giờ thì lần mở Dagster sau chạy bù **một** lần (Dagster chỉ xét lần hẹn gần nhất bị lỡ với lịch không chia partition — đọc trong mã nguồn Dagster 1.13, chưa thử tắt máy thật). Không dùng Task Scheduler của Windows.

## Truy cập và phân quyền

- **Mạng (chốt 23/10/2026, thay cách vào qua Wi-Fi nhà chốt 22/10/2026):** app chạy trên laptop, **mọi server nghe `127.0.0.1`** (web, model, Postgres, Dagster). Máy khác vào qua **Tailscale**: `tailscale serve --bg 8000` đưa web ra mạng riêng bằng HTTPS. Không Funnel, không mở cổng nào ra internet, không cần domain. Luật tường lửa cổng 8000 cho Wi-Fi nhà không cần nữa.
- **Đăng nhập (chốt 23/10/2026):** ai vào được tailnet thì tự đăng ký được bằng email + mã OTP. Chi tiết từng phần — theo OWASP:
  - **Mật khẩu:** 12–128 ký tự, băm Argon2id; băm lại khi thông số thư viện đổi (`check_needs_rehash`). Không bao giờ ghi mật khẩu, mã OTP, mã phiên ra log.
  - **Đăng nhập sai:** 5 lần trong 15 phút với một email → khoá tạm email đó 15 phút (tính cả email không có tài khoản). Email không có tài khoản vẫn chạy một lần băm giả → thời gian trả lời như nhau.
  - **Phiên:** mã ngẫu nhiên 256 bit (`secrets`), database chỉ giữ SHA-256. Tạo phiên mới mỗi lần đăng nhập. Hết hạn sau **7 ngày không dùng**, tối đa **30 ngày** (chốt 23/10/2026 — dài hơn mức OWASP gợi ý cho app rủi ro thấp vì máy riêng, mạng riêng). Đăng xuất xoá phiên trên server; đặt lại mật khẩu xoá mọi phiên của tài khoản.
  - **Cookie:** `__Host-phien; Secure; HttpOnly; SameSite=Lax; Path=/`. `Lax` chứ không `Strict`: mở link từ Zalo vẫn còn đăng nhập.
  - **CSRF:** mọi POST phải có `Sec-Fetch-Site` là `same-origin` / `none`; trình duyệt không gửi header này thì `Origin` phải là địa chỉ của app (`WEB_PUBLIC_ORIGIN`); thiếu cả hai → từ chối. Thêm mã CSRF theo phiên trong mọi form và header `X-CSRF-Token` của mọi `fetch`.
  - **OTP:** 6 chữ số, hết hạn 10 phút, dùng một lần, sai 5 lần thì huỷ mã. Mỗi email: cách nhau ít nhất 60 giây, tối đa 5 mã mỗi giờ; cả app tối đa 30 email mỗi giờ (giữ tài khoản Gmail gửi không bị khoá). Mọi trường hợp (email đã có / chưa có / vượt giới hạn) trả **cùng một câu**, email gửi ở nền nên thời gian trả lời như nhau. Đăng ký bằng email đã có tài khoản → email nhắc dùng "Quên mật khẩu", không có mã.
  - **Header:** `Content-Security-Policy` chỉ cho script / style / ảnh từ chính app (`'self'`, ảnh `data:` cho favicon) — không script nội tuyến; `frame-ancestors 'none'`; `X-Content-Type-Options: nosniff`; `Referrer-Policy: same-origin`.
  - **Khung debug** chỉ hiện cho tài khoản `is_admin`. Không dựa vào địa chỉ `127.0.0.1` nữa: sau `tailscale serve`, mọi request đều tới từ `127.0.0.1`.
- **Lịch sử theo người:** mỗi cuộc hội thoại có chủ (`conversations`). Mọi lần đọc hoặc ghi một cuộc hội thoại, một câu trả lời, một đánh giá đều kiểm chủ sở hữu trong câu SQL — đổi mã trên trình duyệt không xem được hội thoại của người khác. Nút xoá chỉ ẩn khỏi danh sách (chốt 23/10/2026); xoá hẳn bằng `manage_users.py` trên laptop (ví dụ lỡ nhập tên khách).
- **Database:** app kết nối bằng user riêng `taxassistant`, chỉ có quyền trên database `taxassistant` (quyền kết nối của PUBLIC bị thu hồi). Tài khoản `postgres` chỉ dùng cho `create_app_user.sql`.
- **Bí mật** (mật khẩu DB, `AUTH_SECRET`, mật khẩu SMTP) chỉ nằm trong `.env`, không bao giờ vào code hay git.
- **Dữ liệu của khách:** câu hỏi của mẹ được trả lời bằng model chạy trên laptop, **không ra khỏi máy**. Mẹ vẫn hỏi không nêu tên khách; giao diện có dòng nhắc.
- **Bí mật của đăng nhập** (`AUTH_SECRET` — khoá HMAC của mã OTP; `SMTP_USER`, `SMTP_PASSWORD` — App Password của Gmail gửi mã) chỉ nằm trong `.env`. App Password bị Google thu hồi khi đổi mật khẩu tài khoản Google → tạo lại.

## Model AI

- **Rẽ nhánh theo loại câu hỏi bằng cạnh có điều kiện của LangGraph** (chốt 23/10/2026) — đồ thị vẫn cố định: **chào hỏi / không phải câu hỏi** → câu trả lời mẫu, không tìm, không gọi model; **khái niệm** ("X là gì", "khái niệm X", "X nghĩa là") → tra thẳng khoản "X là …" trong Điều "Giải thích từ ngữ" **hoặc Điều mang đúng tên khái niệm** (Luật Quản lý thuế 108/2025 đặt "Điều … Hóa đơn điện tử", khoản 1 "Hóa đơn điện tử là …") của văn bản dùng được tại mốc hỏi, trả lời bằng chính đoạn trích; không thấy thì đi luồng thường; **còn lại** → luồng thường. Nhận loại bằng quy tắc, không bằng model.
- **Quy trình cố định trong code, không phải agent.** Model không tự quyết "tìm thêm". Lý do: thời gian mỗi câu hỏi dự đoán được, bước kiểm trích dẫn luôn chạy, lỗi truy được về đúng bước. Điều phối bằng **LangGraph** (chốt 21/10/2026) với các cạnh cố định; phần dữ liệu và kiểm trích dẫn là code của dự án.
- **Hội thoại nhiều lượt** (chốt 21/10/2026): mỗi cuộc hội thoại là một `thread_id`. Lượt sau mang sang các **ô có cấu trúc** của lượt trước (loại thuế, đối tượng, văn bản đang bàn, mốc thời gian) và chỉ thay ô mà câu mới nêu — mốc thời gian vẫn đọc bằng quy tắc. Không đưa cả lịch sử hội thoại vào model (ngữ cảnh 4B có hạn).
- **Quy tắc dùng LangGraph:** (1) `answers` là bản ghi chính thức, checkpoint chỉ là trạng thái lúc chạy; (2) `questions.thread_id` nối hai nơi; (3) `durability="async"` — ghi checkpoint song song với bước sau, không chặn luồng; (4) luôn đặt `LANGGRAPH_STRICT_MSGPACK=true` (README của checkpointer cảnh báo đọc lại checkpoint có thể bị lợi dụng chạy code); (5) ghim phiên bản LangGraph trong `pyproject.toml`; (6) xoá lịch sử của mẹ phải xoá cả hai nơi. Kết nối của checkpointer phải có `autocommit=True` và `row_factory=dict_row` (theo README).
- **Các bước:** lấy mốc thời gian bằng quy tắc + model trên máy phân loại loại thuế, loại câu hỏi (ép JSON schema) → tìm kiếm kết hợp → lọc theo hiệu lực tại mốc, xếp văn bản luật trước công văn → xếp lại bằng model chạy trên máy (ĐỀ XUẤT: cross-encoder như bge-reranker-v2-m3 — **chỉ thêm khi số đo cho thấy cần**: Điều đúng có trong top 20 nhưng rơi khỏi top 5) → **kéo Điều được dẫn chiếu** → model trên máy viết câu trả lời → kiểm từng trích dẫn với `chunk_positions`.
- **Câu trả lời chạy ra từng chữ** (chốt 23/10/2026, người dùng yêu cầu — thay quy tắc "chỉ hiện sau khi kiểm trích dẫn"): `write_answer` gọi model ở chế độ stream (`call_local_model.stream_local_model_json`), đọc dần chuỗi JSON đang viết để lấy phần kết luận (hoặc từng ý) và đẩy ra bằng `get_stream_writer` của LangGraph (`stream_mode="custom"`); web gửi tiếp cho trình duyệt. Bản đang viết **luôn mang nhãn "Đang viết — chưa kiểm căn cứ"**, không có khối căn cứ; khi các bước kiểm xong, bản đã kiểm (căn cứ, nhãn, cờ con số) **thay thế** bản đang viết. Bản chính thức vẫn là bản đã kiểm, lưu ở `answers`.
- **Tách câu hỏi nhiều ý** (chốt 23/10/2026 — người dùng: câu hỏi phân tích như "khoản chi nào được trừ, khoản nào bị loại, cần bổ sung hồ sơ gì, rủi ro truy thu, xử phạt" cần 5–6 mảng luật; tìm một lần chỉ ra 4 Điều của một hai mảng): bước cố định giữa hiểu câu hỏi và tìm, không phải agent. **Quy tắc trước:** câu dưới 30 từ và một dấu hỏi, hoặc câu hỏi nối tiếp → giữ nguyên, không gọi model. Câu dài → model tách thành 2–5 câu tìm kiếm ngắn dùng thuật ngữ văn bản luật (T=0, JSON schema). Mỗi câu tìm riêng, lấy 2 Điều đầu của mỗi câu theo lượt, bỏ trùng, tối đa 8 Điều. Câu tách ra **chỉ dùng để tìm** — không đưa vào câu trả lời như dữ kiện, hiện ở khung debug. Ngữ cảnh model vẫn ≤ 30.000 ký tự: nhiều Điều thì mỗi Điều được ít chữ hơn. Model được dặn trả lời lần lượt từng ý; dữ kiện câu hỏi chưa nêu thì chia nếu–thì và nói rõ cần thêm dữ kiện gì, không giả định. Giới hạn đã biết: model 4B, ngữ cảnh 16K — câu phân tích dài chạm trần chất lượng của model nhỏ.
- **Kéo Điều được dẫn chiếu** (chốt 23/10/2026 — 4.610/16.878 đoạn, 27%, có câu kiểu "khoản 2 Điều 9"; chỉ đưa Điều đang có thì model trả lời thiếu nửa quy định): với các Điều tìm được, tìm dẫn chiếu bằng quy tắc; chỉ nhận dẫn chiếu **trong cùng văn bản** ("Điều 9", "Điều 9 Luật này", "khoản 2 Điều 9 của Nghị định này"), bỏ dẫn chiếu sang văn bản khác ("Điều 9 Luật Quản lý thuế") và mọi dẫn chiếu trong **văn bản sửa đổi** (số Điều ở đó là của văn bản bị sửa). Có số khoản thì chỉ đưa khoản đó (vị trí lấy từ `chunk_positions`). Tối đa 2 Điều thêm, mỗi Điều tối đa 3.000 ký tự; thêm vào cuối danh sách, trích dẫn vẫn qua đủ guardrail. Lưu ở dạng quan hệ trong database thì để sau, khi web cần hiện "Điều này được dẫn chiếu bởi…" — kiểu GraphRAG của Microsoft (model tự rút thực thể) **không dùng**: câu hỏi của mẹ cụ thể, không phải câu hỏi tổng quát cả kho; quan hệ luật đã ghi sẵn trong chữ.
- **Văn bản bị văn bản mới tuyên bố hết hiệu lực** (chốt 23/10/2026 — người dùng: luôn ưu tiên văn bản có hiệu lực theo thời gian, dù luật cũ lọt vào là do cổng dữ liệu hay do dự án): Điều hiệu lực của văn bản mới thường ghi "Luật Quản lý thuế số 38/2019/QH14 … hết hiệu lực thi hành kể từ ngày Luật này có hiệu lực thi hành" (Luật 108/2025, khoản 3 Điều 52), trong khi cổng Bộ Tư pháp chưa ghi ngày hết hiệu lực cho văn bản cũ. Đọc câu đó bằng quy tắc thành quan hệ `thay_the`. Tại mốc hỏi từ ngày đó trở đi, văn bản cũ và bản hợp nhất của nó (khi **mọi** văn bản gốc của bản hợp nhất đều đã bị thay bởi văn bản ngoài nhóm gốc) **vẫn tìm được** (còn ngoại lệ "trừ …", quy định chuyển tiếp, câu hỏi về năm cũ) nhưng **xếp sau mọi văn bản khác**, và **ghi rõ cho người đọc**: "Đã hết hiệu lực từ 01/07/2026 theo khoản 3 Điều 52 Luật 108/2025/QH15 — cổng dữ liệu chưa ghi" — trên từng căn cứ, trong đoạn đưa cho model, ở trang Tra cứu. Mốc hỏi trước ngày đó thì văn bản cũ dùng bình thường. Không đọc: câu trong văn bản hợp nhất (chép lại từ văn bản gốc), mục chỉ hết hiệu lực một phần ("Điều 1 Nghị định …", "Chương I …"), văn bản nguồn không rõ ngày có hiệu lực, văn bản thứ hai trở đi trong câu khi nó nằm sau phần mô tả ("… hướng dẫn Luật …, Nghị định số 123/2020" — dễ nhầm văn bản được nhắc với văn bản bị thay). Bỏ sót thì an toàn hơn gắn nhầm.
- **Khoản thu bị chấm dứt** (chốt 23/10/2026 — mẹ hỏi "2026 còn phải nộp thuế môn bài ko"): khoản 7 Điều 10 Nghị quyết 198/2025/QH15 ghi "Chấm dứt việc thu, nộp lệ phí môn bài từ ngày 01 tháng 01 năm 2026" — không nêu số hiệu văn bản nào. Đọc câu "Chấm dứt (việc) thu, nộp <khoản thu> từ ngày …" thành quan hệ `cham_dut` tới **mọi văn bản có tên chứa đúng cụm đó** ("lệ phí môn bài"), ban hành trước văn bản tuyên bố. Tại mốc từ ngày đó: các văn bản này xếp sau như văn bản bị thay, mang nhãn **"Không còn áp dụng từ 01/01/2026 theo khoản 7 Điều 10 Nghị quyết 198/2025/QH15: «Chấm dứt việc thu, nộp …»"**; và vì Điều 10 của nghị quyết dài, gom nhiều chính sách (đo: không lọt top 20 khi tìm theo nghĩa), **khoản tuyên bố được kéo vào ngữ cảnh** mỗi khi một văn bản bị chấm dứt có trong danh sách ứng viên tìm được (kể cả ngoài 5 Điều đưa model) — bước kéo Điều được dẫn chiếu làm việc này.
- **Ưu tiên văn bản hợp nhất** (chốt 22/10/2026 — văn bản hợp nhất thường đầy đủ hơn văn bản riêng lẻ): tại mốc hỏi, văn bản gốc đã có bản hợp nhất có chữ thì tìm trên bản hợp nhất mới nhất ban hành **không sau** mốc hỏi; ẩn văn bản gốc và các bản hợp nhất cũ hơn. Bản hợp nhất ban hành sau mốc hỏi không dùng — nó gộp cả sửa đổi đến sau.
- **Embedding chạy trên máy**, không qua API.
- **Hiểu câu hỏi** (chốt 18/10/2026):
  - **Mốc thời gian:** quy tắc (regex) trên các mẫu câu như "năm 2025", "trước 1/7/2025", "hiện nay". Không đọc được thì dùng hôm nay và ghi rõ. Mỗi mẫu câu có test. "Năm YYYY" của năm đã qua → 31/12/YYYY; **năm hiện tại → hôm nay** (chốt 23/10/2026 — "năm 2026 có được gia hạn" hỏi lúc 23/10/2026 bị quy thành 31/12/2026, đúng sau ngày NĐ 245/2026 hết hiệu lực 30/12/2026 → bộ lọc loại mất văn bản đúng).
- **Đưa model 5 Điều** (từ 23/10/2026, trước là 4) — khớp chỉ số recall@5 của bộ đo. Câu "hạn cuối thuế đất phi nông nghiệp": Điều đúng (Điều 21 NĐ 252/2026) đứng #1 theo nghĩa nhưng #5 sau khi gộp với từ khoá → bị cắt ở 4.
- **Văn bản chỉ áp dụng trong một năm** (chốt 23/10/2026): tiêu đề "… trong năm YYYY" (nghị định gia hạn nộp thuế hằng năm) mà cổng **không ghi** ngày hết hiệu lực → coi như hết hiệu lực từ 01/01/YYYY+1, ở cả tìm kiếm lẫn trang Tra cứu. Cổng có ghi ngày thì dùng ngày của cổng. Đo trên toàn kho: 8 tiêu đề có cụm này — 6 nghị định gia hạn, 2 văn bản cũ đã hết hiệu lực; chỉ 64/2024/NĐ-CP và 82/2025/NĐ-CP bị đổi (trước đó vẫn được coi còn hiệu lực năm 2026, lấn nghị định 245/2026).
- **Thời hạn rơi vào ngày nghỉ** (chốt 23/10/2026, `add_deadline_rule.py` — câu "hạn cuối thuế đất phi nông nghiệp": 31/10/2026 là thứ Bảy, model 4B không tự tính thứ): câu hỏi nói về thời hạn (thời hạn, hạn cuối, hạn nộp, chậm nhất…) → (1) luôn thêm Điều có quy tắc "ngày cuối cùng của thời hạn trùng với ngày nghỉ … tính là ngày làm việc liền kề sau" của văn bản còn hiệu lực tại mốc (hiện là Điều 3 NĐ 252/2026) vào ngữ cảnh; (2) code tính sẵn lịch: ngày "D tháng M" trong các đoạn tìm được, ở năm của mốc, rơi vào thứ Bảy, Chủ nhật hoặc ngày lễ dương lịch cố định (1/1, 30/4, 1/5, 2/9) → ghi "31/10/2026 là thứ Bảy → tính là thứ Hai 02/11/2026" vào ngữ cảnh; (3) sau khi kiểm trích dẫn, ngày nghỉ nào được nhắc trong kết luận mà kết luận chưa nêu ngày lùi thì code tự thêm dòng lịch vào cuối kết luận. **Chưa tính** Tết âm lịch, Giỗ Tổ, ngày nghỉ bù — cần bảng ngày nghỉ từng năm (câu hỏi mở).
  - **Loại thuế, loại câu hỏi:** tạm dùng model viết câu trả lời (Qwen) với đầu ra ép theo JSON schema. Khi đủ vài trăm câu có nhãn (từ mẹ và quy tắc): fine-tune một encoder nhỏ chạy trên máy (thử mmBERT-small và BamiBERT, PhoBERT-base làm mốc; embedding + logistic regression là mốc rẻ nhất), so với cách tạm thời trên cùng bộ đo, ngang thì thay. Mục đích: một bước tất định làm nền cho debug — cùng câu hỏi ra cùng nhãn, có xác suất. Chi tiết và cách phân loại lỗi: `danh-gia.md` mục 4b và 6.
  - **Loại thuế chỉ dùng để ưu tiên kết quả, không lọc cứng.** Phân loại sai mà lọc cứng thì Điều đúng bị loại khỏi kết quả tìm kiếm.
- **Mọi lời gọi model nằm ở một chỗ duy nhất** (chốt 08/10/2026). Nói theo API kiểu OpenAI của `llama-server`, nên đổi sang vLLM/SGLang trên VPS chỉ đổi địa chỉ.

## Chi phí và hiệu năng

- **App không còn chi phí API** (từ 21/10/2026): model chạy trên laptop. Bỏ trần ngân sách 300.000đ/tháng và giới hạn số câu mỗi 5 tiếng; trang chi phí thành **trang hiệu năng** (thời gian trả lời, số câu, bộ nhớ GPU).
- **Khi lên VPS có GPU:** tiền thuê GPU thành chi phí chính — đặt lại ngân sách lúc đó.

## Chạy ở đâu

- **Giai đoạn đầu:** laptop, qua Tailscale.
- **Tự host** (chốt 21/10/2026): `llama-server` trên laptop.
- **Giai đoạn sau:** lên VPS có GPU, chạy vLLM hoặc SGLang (cần Linux), có thể dùng model lớn hơn (Qwen3.5-9B) nếu bộ đo cho thấy cần.
- **Khi lên VPS:** VPS thường không có GPU → chạy embedding bằng CPU, hoặc dùng dịch vụ embedding qua API và tính lại vector cho toàn bộ dữ liệu (việc một buổi). Database chạy trên chính VPS.

## Quy tắc bất biến

Code không bao giờ được phá các quy tắc này. Thấy cần phá → dừng lại, hỏi người dùng.

1. **Không trích dẫn nào hiện ra nếu không khớp từng chữ** với một đoạn đã lưu (`chunk_positions`). Không khớp thì bỏ, không "sửa cho gần đúng".
2. **Chữ OCR không bao giờ được trích.** Đoạn có `text_origin = 'ocr'` (gồm mọi chữ từ PDF) chỉ dùng để tìm; căn cứ từ đó chỉ hiện số hiệu + link.
3. **Luôn lưu bản gốc ra `data/raw/` trước khi xử lý**, và không sửa bản gốc. Database phải dựng lại được từ bản gốc. Bản gốc bị nguồn sửa thì giữ bản cũ trong `history/`, không ghi đè.
4. **Tôn trọng nguồn dữ liệu:** mọi lần tải đi qua `download_and_save` với khoảng nghỉ `FETCH_DELAY_SECONDS`; tuân thủ robots.txt (không gọi `/api/`, `/Pages/` của vbpl.vn); không vượt CAPTCHA; không dùng thuvienphapluat.vn, luatvietnam.vn; ghi nguồn congbao.chinhphu.vn và gdt.gov.vn.
5. **Mọi câu trả lời gắn với một mốc thời gian** và chỉ dùng căn cứ có hiệu lực tại mốc đó (hoặc gắn nhãn hết hiệu lực).
6. **Bot không kết luận vi phạm.** Câu hỏi vi phạm luôn trả lời dạng nếu–thì, đủ mọi trường hợp, mỗi cách xử lý có căn cứ riêng.
7. **Mọi lời gọi model đi qua một chỗ duy nhất**, và mỗi lời gọi ghi `usage_log` (token, thời gian chạy).
8. **Bí mật không vào code, log hay git.** `.env` không bao giờ được commit.
9. **App dùng user `taxassistant`**, không dùng `postgres`.
10. **Không công đoạn dùng model nào được đưa vào dùng khi chưa có bài đo trong `danh-gia.md` và chưa có kết quả mốc gốc.** Mỗi lần đổi prompt, model hay cách tìm kiếm phải đo lại, và chỉ số chính không được xấu đi.
11. **Một văn bản lỗi không được làm hỏng cả công đoạn.** Mỗi văn bản tự bắt lỗi của mình, lỗi được ghi kèm id và lý do, công đoạn chạy tiếp. Công đoạn chỉ dừng khi nguồn có dấu hiệu sập (nhiều lỗi liên tiếp) — và khi đó báo lỗi rõ ràng, không `sys.exit`.
12. **Thông tin quyết định câu trả lời đúng hay sai được lấy bằng cách tất định khi làm được** (quy tắc, so khớp, tra bảng). Model chỉ dùng ở chỗ quy tắc không làm được; kết quả của model phải đo được đúng sai trên bộ có nhãn, và không được dùng để lọc cứng căn cứ.
13. **Không dùng đầu ra của Claude** (câu trả lời, nhãn, điểm chấm, tóm tắt suy luận) **làm dữ liệu huấn luyện bất kỳ model nào**, trừ khi Anthropic cho phép bằng văn bản. Căn cứ: Usage Policy của Anthropic ("Use outputs to train an AI model (e.g., "model scraping" or "model distillation") without prior authorization"), Commercial Terms mục D.4. Dữ liệu huấn luyện chỉ lấy từ mẹ, từ quy tắc, từ dữ liệu luật, và từ model có giấy phép mở.
14. **Mọi đường dẫn cần phiên đăng nhập, trừ danh sách công khai** (đăng nhập, đăng ký, quên mật khẩu, `/static`) — chặn ở một middleware, không kiểm rải rác từng route. Mọi câu SQL đọc / ghi dữ liệu của người dùng có điều kiện chủ sở hữu (`user_id`). Mật khẩu, mã OTP, mã phiên không bao giờ lưu dạng gốc hay ghi ra log.
15. **Câu trả lời của model không tự thành dữ liệu huấn luyện.** Chỉ dùng câu hỏi của tài khoản `allow_training`; chỉ câu trả lời được người hỏi chấm `dung` mới làm đích huấn luyện, câu `sai` / `chua_du` chỉ làm dữ liệu đánh giá hoặc cần sửa tay trước. Tập đánh giá chia **theo cuộc hội thoại** và cố định (`danh-gia.md`, Dữ liệu từ lịch sử hỏi đáp).

## Rủi ro đã biết

1. **Cổng JSON của Bộ Tư pháp có thể tắt bất cứ lúc nào** — không có tài liệu công bố, tên máy chủ có chữ "bientap". → Luôn lưu bản gốc, có nguồn dự phòng congbao.
2. **Lịch sử sửa đổi không đầy đủ.** "Điều nào bị sửa khi nào" chỉ có trong chú thích văn bản hợp nhất, rất không đều — có văn bản 0 chú thích, có văn bản 123. Văn bản chưa được hợp nhất thì không biết lịch sử.
3. **Luật bị sửa tới từng cụm từ.** Một nghị định đổi "500 triệu đồng" thành "01 tỷ đồng" ở 18 chỗ cùng lúc. Theo dõi lịch sử theo điều/khoản chỉ là gần đúng.
4. **Lấy công văn lần đầu dễ hỏng** (467 trang, chuyển trang phụ thuộc phiên). Cập nhật hằng tuần thì dễ.
5. **Mẹ có thể đọc "cách xử lý" như kết luận**, dù bot trình bày dạng nếu–thì. Chỉ biết khi bà dùng thật.
6. **Bộ tách Điều có giới hạn:** ngoặc kép không đóng trong văn bản sửa đổi làm các Điều sau nhập vào Điều đang mở; 365 Điều dài hơn 2.000 từ. Chi tiết ở `nguon-du-lieu.md`.

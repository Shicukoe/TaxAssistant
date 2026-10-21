# Kiến trúc

Cập nhật: 15/10/2026. Muốn đổi một lựa chọn ở đây thì sửa file này trước, rồi mới sửa code.

## Công nghệ

| Lớp | Chọn | Vai trò / vì sao |
|---|---|---|
| Ngôn ngữ | **Python 3.12** | Phần nặng (đọc PDF, OCR, chạy model trên GPU) đều mạnh nhất ở Python. Một ngôn ngữ, một chương trình |
| Web | **FastAPI**, HTML/CSS/JS thuần render từ server (Jinja2) | Không cần bước build, không framework frontend |
| Database | **PostgreSQL 18** ngay từ đầu | Không phải chuyển database khi lên server |
| Truy cập database | **psycopg 3**, SQL viết tay | Không ORM — schema nhỏ, một người viết |
| Tìm kiếm | **Kết hợp** tìm theo từ khóa (full-text, bỏ dấu bằng `unaccent`) + tìm theo nghĩa (vector), gộp bằng reciprocal rank fusion | Mỗi cách bắt được những câu cách kia bỏ sót |
| Lưu vector | **pgvector** trong Postgres | Không cần Qdrant — chữ, vị trí trích dẫn và vector ở cùng một chỗ, một câu SQL làm được cả lọc hiệu lực lẫn tìm |
| Embedding | Model chạy trên **GPU RTX 3060 Laptop (6 GB)** | Miễn phí. Model cụ thể chọn sau khi đo ở bước Tìm kiếm |
| OCR | **Tesseract**, gói tiếng Việt `vie` (chốt 13/10/2026) | Nhẹ, chạy bằng CPU. Unlimited-OCR (~6,7 GB) không vừa GPU 6 GB. Độ chính xác đo theo `danh-gia.md` |
| Model AI | **Tự host trên laptop** (chốt 21/10/2026): **Qwen3.5-4B** bản GGUF lượng tử 4-bit (`Q4_K_M`, file 2,74 GB) — ĐỀ XUẤT, chốt sau khi đo — viết câu trả lời và tạm thời phân loại câu hỏi. **Mốc thời gian lấy bằng quy tắc, không dùng model** (chốt 18/10/2026). Không dùng Claude API trong app | Học tự host, câu hỏi của mẹ không ra khỏi máy. Bản 9B không vừa 6 GB VRAM |
| Chạy model | **llama.cpp `llama-server`** (chốt 21/10/2026), bản dựng sẵn Windows CUDA 12.4 (khớp driver 552.44) | API kiểu OpenAI, ép đầu ra theo JSON schema; mọi tham số (context, số lớp lên GPU, KV cache) là cờ lệnh rõ ràng. File model để ở ổ D |
| Giám khảo bộ đo | **Claude** (chốt 21/10/2026), **chỉ** dùng khi chạy bộ đo, không dùng trong app | Model viết câu trả lời không tự chấm mình. Điểm của Claude không bao giờ làm dữ liệu huấn luyện (quy tắc số 13) |
| Cấu hình | **python-dotenv**, file `.env` | Bí mật không nằm trong code |
| Điều phối luồng trả lời | **LangGraph** (chốt 21/10/2026): `StateGraph`, checkpointer Postgres (`langgraph-checkpoint-postgres`), `stream_mode` để gửi tiến độ và từng token lên giao diện, `RetryPolicy` cho lỗi kết nối, `TimeoutPolicy` | Có sẵn lưu trạng thái cho hội thoại nhiều lượt, xem lại state sau từng bước, chạy lại từ một bước. Không dùng agent dựng sẵn, Deep Agents, LangSmith, vector store của LangChain |
| Điều phối pipeline | **Dagster** (chốt 15/10/2026) | Mỗi công đoạn là một asset: log riêng từng công đoạn, công đoạn lỗi thì bước sau dừng còn bước độc lập vẫn chạy, có kiểm chất lượng dữ liệu (asset check) và giao diện web xem lịch sử chạy |
| Truy cập từ xa | **VPN mạng riêng** kiểu Tailscale | Không mở gì ra internet |

## Ranh giới thư mục

- `app/config.py` — đọc `.env`, chứa mọi hằng số cấu hình (kết nối DB, địa chỉ `llama-server`, tốc độ tải, tên model, bảng giá giám khảo). Nơi duy nhất đọc biến môi trường.
- `app/db/` — schema và công cụ database: `create_app_user.sql` (chạy một lần bằng tài khoản quản trị), `setup_database.py` (tạo database, chạy migration), `check_database.py` (bài tự kiểm), `migrations/` (file `.sql` đánh số, chỉ đi tiến).
- `app/ingest/` — lấy văn bản về và đưa vào database. Chỉ ghi các bảng văn bản (`documents`, `provisions`, `chunks`, `chunk_positions`, sau này `amendments`, `embeddings`). Không gọi model AI.
  - `download_moj_documents.py` — sitemap vbpl.vn → JSON cổng Bộ Tư pháp + file đính kèm → `data/raw/moj/`
  - `download_from_congbao.py` — nguồn dự phòng cho văn bản cổng Bộ Tư pháp không có → `data/raw/congbao/`
  - `split_articles.py` — HTML → Điều / khoản / điểm kèm vị trí ký tự. Không đọc mạng, không ghi DB
  - `save_to_database.py` — bản lưu trên đĩa → database
  - `stage_report.py` — báo cáo của một công đoạn: đếm kết quả, danh sách lỗi từng văn bản
- `app/pipeline/` — nối các công đoạn của `app/ingest/` thành pipeline Dagster (`definitions.py`). Chỉ gọi hàm có sẵn, không chứa logic tải hay tách văn bản.
- `dagster_home/` — nơi Dagster lưu lịch sử chạy và log (không commit, trừ `dagster.yaml`).
- `scripts/run_pipeline.sh` — chạy pipeline một lần, hoặc mở Dagster (`ui`): giao diện web + bộ hẹn giờ chạy hằng tuần. Bash: Git Bash trên Windows, Linux trên VPS. Giải thích Dagster và cách xem lỗi: `pipeline-du-lieu.md`.
- `data/raw/` — bản gốc tải về (không commit). Chỉ thêm, không sửa: bản bị cổng sửa thì bản cũ chuyển vào `data/raw/moj/history/{id}/{ngày}.json`.
- `docs/` — tài liệu thiết kế.

Dự kiến, **chưa có** (đặt tên khi tới bước tương ứng):

- thư mục tìm kiếm (bước Tìm kiếm) — đọc DB, không gọi model viết câu trả lời
- thư mục trả lời (bước Trả lời) — **chỗ duy nhất gọi model AI**, kiểm trích dẫn, ghi token và thời gian chạy
- thư mục web (bước Giao diện) — FastAPI + template; không chứa logic tìm kiếm hay gọi model trực tiếp

## Lưu trữ

- **PostgreSQL** (database `taxassistant`): 10 bảng, mỗi bảng có chú thích lý do trong `app/db/migrations/001_create_tables.sql`.
  - `documents` — một văn bản: số hiệu, loại, ngày, hiệu lực, nguồn, link gốc, `text_origin` (`native` / `ocr` / `none`)
  - `document_relations` — văn bản này sửa / thay thế / hướng dẫn văn bản kia
  - `provisions` — từng Điều / khoản / điểm
  - `chunks` — đoạn dùng để tìm kiếm: một Điều trọn vẹn
  - `chunk_positions` — vị trí ký tự của từng khoản/điểm trong đoạn → dùng để kiểm trích dẫn
  - `amendments` — lịch sử sửa đổi lấy từ chú thích văn bản hợp nhất, tới mức cụm từ
  - `embeddings` — vector của từng đoạn
  - `questions`, `answers` — lịch sử hỏi đáp, **bản ghi chính thức** (lịch sử của mẹ, bộ đo, trang hiệu năng chỉ đọc ở đây). `questions` sẽ có `thread_id` nối sang checkpoint (migration khi viết bước Trả lời)
  - bảng checkpoint của LangGraph (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, do `.setup()` tạo) — **trạng thái lúc chạy**, gồm cả bản nháp trước guardrail. Không hiển thị câu trả lời từ đây. Giá trị đơn giản (mốc thời gian, loại thuế) đọc được bằng JSONB; list/dict nằm ở `checkpoint_blobs` (msgpack), đọc bằng `get_state_history`
  - `usage_log` — token, thời gian chạy (và chi phí, với lời gọi giám khảo Claude) của từng lần gọi model
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

**Văn bản chỉ có file đính kèm** (22% văn bản trên cổng JSON) → tải file về lưu bản gốc. (chốt 02/10/2026)

**Mọi chữ lấy từ PDF đều coi là OCR** — chỉ để tìm, không trích. Nhiều PDF là bản scan đã OCR sẵn, chữ sai kiểu "QUYÉT ĐỊNH", và không có cách chắc chắn biết PDF nào là chữ gốc. Chỉ chữ từ HTML của cổng và từ file DOC/RTF mới được trích nguyên văn. (chốt 02/10/2026)

**Cập nhật** hằng tuần, tự động bằng lịch của Dagster (`cap_nhat_hang_tuan` trong `app/pipeline/definitions.py`, thứ Hai 9:00 giờ Việt Nam). Lịch chỉ chạy khi Dagster đang mở (`run_pipeline.sh ui`). Máy tắt lúc tới giờ thì lần mở Dagster sau chạy bù **một** lần (Dagster chỉ xét lần hẹn gần nhất bị lỡ với lịch không chia partition — đọc trong mã nguồn Dagster 1.13, chưa thử tắt máy thật). Không dùng Task Scheduler của Windows.

## Truy cập và phân quyền

- **Giai đoạn đầu:** app chạy trên laptop. Mẹ truy cập qua VPN mạng riêng — không mở cổng nào ra internet, chưa cần đăng nhập, chưa cần domain. Ai vào được mạng riêng là vào được app.
- **Database:** app kết nối bằng user riêng `taxassistant`, chỉ có quyền trên database `taxassistant` (quyền kết nối của PUBLIC bị thu hồi). Tài khoản `postgres` chỉ dùng cho `create_app_user.sql`.
- **Bí mật** (mật khẩu DB, API key của giám khảo) chỉ nằm trong `.env`, không bao giờ vào code hay git.
- **Dữ liệu của khách:** câu hỏi của mẹ được trả lời bằng model chạy trên laptop, **không ra khỏi máy** (từ 21/10/2026). Ngoại lệ duy nhất: các câu trong **bộ câu hỏi kiểm tra** (lấy từ câu hỏi thật, đã bỏ tên khách) được gửi lên API của Anthropic khi chạy giám khảo. Mẹ vẫn hỏi không nêu tên khách; giao diện có dòng nhắc.
- **Khi có nhiều người dùng:** đăng nhập và tách lịch sử theo tài khoản — chưa thiết kế, làm khi lên VPS.

## Model AI

- **Quy trình cố định trong code, không phải agent.** Model không tự quyết "tìm thêm". Lý do: thời gian mỗi câu hỏi dự đoán được, bước kiểm trích dẫn luôn chạy, lỗi truy được về đúng bước. Điều phối bằng **LangGraph** (chốt 21/10/2026) với các cạnh cố định; phần dữ liệu và kiểm trích dẫn là code của dự án.
- **Hội thoại nhiều lượt** (chốt 21/10/2026): mỗi cuộc hội thoại là một `thread_id`. Lượt sau mang sang các **ô có cấu trúc** của lượt trước (loại thuế, đối tượng, văn bản đang bàn, mốc thời gian) và chỉ thay ô mà câu mới nêu — mốc thời gian vẫn đọc bằng quy tắc. Không đưa cả lịch sử hội thoại vào model (ngữ cảnh 4B có hạn).
- **Quy tắc dùng LangGraph:** (1) `answers` là bản ghi chính thức, checkpoint chỉ là trạng thái lúc chạy; (2) `questions.thread_id` nối hai nơi; (3) `durability="async"` — ghi checkpoint song song với bước sau, không chặn luồng; (4) luôn đặt `LANGGRAPH_STRICT_MSGPACK=true` (README của checkpointer cảnh báo đọc lại checkpoint có thể bị lợi dụng chạy code); (5) ghim phiên bản LangGraph trong `pyproject.toml`; (6) xoá lịch sử của mẹ phải xoá cả hai nơi. Kết nối của checkpointer phải có `autocommit=True` và `row_factory=dict_row` (theo README).
- **Các bước:** lấy mốc thời gian bằng quy tắc + model trên máy phân loại loại thuế, loại câu hỏi (ép JSON schema) → tìm kiếm kết hợp → lọc theo hiệu lực tại mốc, xếp văn bản luật trước công văn → xếp lại bằng model chạy trên máy (ĐỀ XUẤT: cross-encoder như bge-reranker-v2-m3 — chọn ở bước Tìm kiếm) → model trên máy viết câu trả lời → kiểm từng trích dẫn với `chunk_positions`.
- **Embedding chạy trên máy**, không qua API.
- **Hiểu câu hỏi** (chốt 18/10/2026):
  - **Mốc thời gian:** quy tắc (regex) trên các mẫu câu như "năm 2025", "trước 1/7/2025", "hiện nay". Không đọc được thì dùng hôm nay và ghi rõ. Mỗi mẫu câu có test.
  - **Loại thuế, loại câu hỏi:** tạm dùng model viết câu trả lời (Qwen) với đầu ra ép theo JSON schema. Khi đủ vài trăm câu có nhãn (từ mẹ và quy tắc — không từ Claude): fine-tune một encoder nhỏ chạy trên máy (thử mmBERT-small và BamiBERT, PhoBERT-base làm mốc; embedding + logistic regression là mốc rẻ nhất), so với cách tạm thời trên cùng bộ đo, ngang thì thay. Mục đích: một bước tất định làm nền cho debug — cùng câu hỏi ra cùng nhãn, có xác suất. Chi tiết và cách phân loại lỗi: `danh-gia.md` mục 4b và 6.
  - **Loại thuế chỉ dùng để ưu tiên kết quả, không lọc cứng.** Phân loại sai mà lọc cứng thì Điều đúng bị loại khỏi kết quả tìm kiếm.
- **Mọi lời gọi model nằm ở một chỗ duy nhất** (chốt 08/10/2026). Nói theo API kiểu OpenAI của `llama-server`, nên đổi sang vLLM/SGLang trên VPS chỉ đổi địa chỉ.

## Chi phí và hiệu năng

- **App không còn chi phí API** (từ 21/10/2026): model chạy trên laptop. Bỏ trần ngân sách 300.000đ/tháng và giới hạn số câu mỗi 5 tiếng; trang chi phí thành **trang hiệu năng** (thời gian trả lời, số câu, bộ nhớ GPU).
- **Chi phí còn lại:** giám khảo Claude khi chạy bộ đo — tính từ `usage` của mỗi phản hồi, ghi `usage_log`. Chỉ chạy bộ đo khi đổi model, prompt hay cách tìm kiếm.
- **Khi lên VPS có GPU:** tiền thuê GPU thành chi phí chính — đặt lại ngân sách lúc đó.

## Chạy ở đâu

- **Giai đoạn đầu:** laptop, qua VPN mạng riêng.
- **Tự host ngay từ bây giờ** (chốt 21/10/2026, thay quyết định 08/10/2026 "Claude API trước"): `llama-server` trên laptop. Lý do: học tự host, xây harness và deploy; đầu ra của Claude không dùng được để huấn luyện model tự host (quy tắc số 13), nên làm trước bằng Claude ít giá trị.
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
7. **Mọi lời gọi model đi qua một chỗ duy nhất**, và mỗi lời gọi ghi `usage_log` (token, thời gian chạy; chi phí với lời gọi giám khảo).
8. **Bí mật không vào code, log hay git.** `.env` không bao giờ được commit.
9. **App dùng user `taxassistant`**, không dùng `postgres`.
10. **Không công đoạn dùng model nào được đưa vào dùng khi chưa có bài đo trong `danh-gia.md` và chưa có kết quả mốc gốc.** Mỗi lần đổi prompt, model hay cách tìm kiếm phải đo lại, và chỉ số chính không được xấu đi.
11. **Một văn bản lỗi không được làm hỏng cả công đoạn.** Mỗi văn bản tự bắt lỗi của mình, lỗi được ghi kèm id và lý do, công đoạn chạy tiếp. Công đoạn chỉ dừng khi nguồn có dấu hiệu sập (nhiều lỗi liên tiếp) — và khi đó báo lỗi rõ ràng, không `sys.exit`.
12. **Thông tin quyết định câu trả lời đúng hay sai được lấy bằng cách tất định khi làm được** (quy tắc, so khớp, tra bảng). Model chỉ dùng ở chỗ quy tắc không làm được; kết quả của model phải đo được đúng sai trên bộ có nhãn, và không được dùng để lọc cứng căn cứ.
13. **Không dùng đầu ra của Claude** (câu trả lời, nhãn, điểm chấm, tóm tắt suy luận) **làm dữ liệu huấn luyện bất kỳ model nào**, trừ khi Anthropic cho phép bằng văn bản. Căn cứ: Usage Policy của Anthropic ("Use outputs to train an AI model (e.g., "model scraping" or "model distillation") without prior authorization"), Commercial Terms mục D.4. Dữ liệu huấn luyện chỉ lấy từ mẹ, từ quy tắc, từ dữ liệu luật, và từ model có giấy phép mở.

## Rủi ro đã biết

1. **Cổng JSON của Bộ Tư pháp có thể tắt bất cứ lúc nào** — không có tài liệu công bố, tên máy chủ có chữ "bientap". → Luôn lưu bản gốc, có nguồn dự phòng congbao.
2. **Lịch sử sửa đổi không đầy đủ.** "Điều nào bị sửa khi nào" chỉ có trong chú thích văn bản hợp nhất, rất không đều — có văn bản 0 chú thích, có văn bản 123. Văn bản chưa được hợp nhất thì không biết lịch sử.
3. **Luật bị sửa tới từng cụm từ.** Một nghị định đổi "500 triệu đồng" thành "01 tỷ đồng" ở 18 chỗ cùng lúc. Theo dõi lịch sử theo điều/khoản chỉ là gần đúng.
4. **Lấy công văn lần đầu dễ hỏng** (467 trang, chuyển trang phụ thuộc phiên). Cập nhật hằng tuần thì dễ.
5. **Mẹ có thể đọc "cách xử lý" như kết luận**, dù bot trình bày dạng nếu–thì. Chỉ biết khi bà dùng thật.
6. **Bộ tách Điều có giới hạn:** ngoặc kép không đóng trong văn bản sửa đổi làm các Điều sau nhập vào Điều đang mở; 365 Điều dài hơn 2.000 từ. Chi tiết ở `nguon-du-lieu.md`.

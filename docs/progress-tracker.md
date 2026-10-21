# Tiến độ

Cập nhật sau mỗi thay đổi đáng kể. Đây là nơi **duy nhất** ghi trạng thái; `ke-hoach.md` chỉ ghi kế hoạch.

Cập nhật: 22/10/2026

## Giai đoạn hiện tại

Bước 1 (Dựng database) và bước 2 (Lấy văn bản luật về) của `ke-hoach.md`.

## Mục tiêu hiện tại

Đưa toàn bộ văn bản thuế trung ương đã tải vào database ở dạng tìm kiếm được.

## Đã xong

- Khảo sát: yêu cầu, nguồn dữ liệu, thiết kế (cắt theo Điều, mô hình thời gian, kiểm trích dẫn, kiểm soát chi phí).
- Schema 10 bảng, `setup_database.py`, `check_database.py`, `create_app_user.sql` (user và database `taxassistant`).
- Tải từ cổng Bộ Tư pháp: 3.159 JSON, 408 file đính kèm cho văn bản JSON rỗng, 95 file máy chủ không có.
- Tải từ congbao: 15 văn bản còn hiệu lực mà cổng Bộ Tư pháp không có chữ, không có file.
- Bộ tách Điều/khoản/điểm: bắt được 99,8% Điều, 98,1% khoản, 98,0% điểm (đo 02/10/2026, lấy markup của cổng làm đáp án).
- **Database dựng xong** (19/10/2026, bước 1 đạt "Xong khi"): user và database `taxassistant` tạo bằng pgAdmin; pgvector 0.8.7 người dùng tự build từ GitHub theo README (Windows); `check_database` in `PASS`. Sửa bài kiểm constraint: trước đây chèn 0 dòng trên database rỗng nên báo sai "constraint không cắn".
- **Nạp database lần đầu** (19/10/2026, ~1 phút): 2.865 văn bản, 12.353 Điều (chunk), 66.551 Điều/khoản/điểm, 0 lỗi; 1.301 văn bản chưa tách được Điều (không có chữ hoặc không chia Điều). Database 123 MB.
- Đo bộ lọc link (08/10/2026): không sót văn bản có "thuế" trong tiêu đề.
- Khảo sát văn bản địa phương (08/10/2026): giữ quyết định chỉ lấy trung ương.
- Tài liệu chuyển sang bộ sáu file theo mẫu, `CLAUDE.md` làm điểm vào (11/10/2026).
- Nghiên cứu thứ bậc văn bản, quy tắc áp dụng, vị trí công văn, đọc từ bản gốc Luật 64/2025, Luật 87/2025, Nghị định 78/2025, Nghị định 30/2020, Pháp lệnh Hợp nhất, Luật Quản lý thuế 108/2025 → `thu-bac-van-ban.md`. Kiểm nguồn thay thế → `nguon-du-lieu.md` (12/10/2026).
- **Pipeline dữ liệu tự động bằng Dagster** (15/10/2026): 5 công đoạn (danh sách → văn bản Bộ Tư pháp → file đính kèm → congbao; database), 6 bài kiểm chất lượng, log riêng từng công đoạn. Mỗi văn bản tự bắt lỗi; tự thử lại lỗi mạng; tải lại văn bản còn hiệu lực và giữ bản cũ trong `history/`; database chỉ nạp lại văn bản đổi (migration 002: `raw_sha256`, `parser_version`). Chạy: `bash scripts/run_pipeline.sh` (thêm `ui` để xem giao diện). Giải thích: `pipeline-du-lieu.md`.
- **Lần chạy thật đầu tiên** (15/10/2026, 69 phút): danh sách 3.168 văn bản, 0 mới. Tải lại 1.602 văn bản còn hiệu lực: 1.239 không đổi, **363 bị cổng sửa** (359 sửa phần nội dung, 4 sửa tiêu đề; trong 359 có 104 chỉ đổi HTML, còn lại đổi chữ, phần lớn là định dạng lại, có cả sửa lỗi chính tả như "a" → "ạ"). Bản cũ lưu ở `history/` (22 MB). 8 văn bản mới cổng trả HTTP 500 cả 3 lần → ghi lỗi, công đoạn chạy tiếp. File đính kèm, congbao: 0 lỗi. Database: lỗi mật khẩu như dự kiến.
- **Model chạy trên laptop** (22/10/2026): llama.cpp `llama-server` bản b11796 (Windows CUDA 12.4) + Qwen3.5-4B `Q4_K_M` của unsloth (Apache-2.0), cả ba file kiểm SHA-256 khớp, để ở `D:/models`. Chạy: `bash scripts/run_model_server.sh`. Đo: server chiếm ~3 GB VRAM (còn ~2 GB), đọc ngữ cảnh ~1.130 token/giây, sinh ~75 token/giây, một câu trả lời 734 token ngữ cảnh + 203 token ra mất 3,4 giây. Ép JSON schema chạy được. CORS giới hạn `localhost` (mặc định mở cho mọi nguồn). `config.py`/`.env.example` đã thay cấu hình Claude cũ bằng `LLM_BASE_URL`, `LLM_MODEL`, `JUDGE_MODEL`.
- **Hai lỗi thật ở lần thử đầu** (chế độ suy luận tắt): (1) hỏi định mức rượu miễn thuế của hành khách bay quốc tế — model trích **đúng nguyên văn** điểm a khoản 4 Điều 6 NĐ 273/2026 nhưng khoản 4 nói về thuyền viên; khoản 2 (hành khách) dẫn sang Điều 6 NĐ 134/2016 → lỗi "suy luận sai", guardrail khớp chữ không bắt được. (2) phân loại "hộ kinh doanh nộp tờ khai chậm 45 ngày bị phạt" thành TNCN/TNDN + "tra cứu" (đúng: hộ kinh doanh + xử phạt, "vi phạm") — JSON đúng khuôn, nhãn sai.
- **So ba mức trên cùng câu hỏi** (22/10/2026, temperature 0): (1) model trần **bịa** — dẫn "Nghị định 42/2024/NĐ-CP", bịa điều kiện "doanh thu dưới 30 tỷ", "thuế suất ưu đãi 2%"; (2) chỉ thêm system prompt — vẫn bịa danh sách "Điều 4…12" khi không có Điều nào được đưa vào; (3) thêm Điều luật — bám căn cứ, nói "không có căn cứ" khi Điều không liên quan, và trả lời **đúng** (20% / 15% / 17%) khi được đưa đúng Điều 10, 13 của 113/VBHN-VPQH. Model chưa theo đúng khuôn (không đặt trích dẫn trong ngoặc kép như dặn). Tìm kiếm full-text thô lấy sai Điều (TNCN, thông tư 2011). Kết luận: chưa cần fine-tune — chất lượng đến từ tìm kiếm + harness.
- Khảo sát Unlimited-OCR (không chọn: ~6,7 GB không vừa GPU). Nghiên cứu phương pháp đánh giá (RAGAS, ALCE, RAGChecker, ARES, Magesh, OHRBench, BEIR…) → `danh-gia.md` (13/10/2026).

## Đang làm

- Lịch chạy hằng tuần: dùng lịch của Dagster (thứ Hai 9:00), không dùng Task Scheduler. Chỉ chạy khi người dùng mở `bash scripts/run_pipeline.sh ui`; lỡ giờ thì chạy bù một lần lúc mở. Đã thử mở bằng Git Bash (16/10/2026): giao diện lên, lịch `RUNNING`, lần kế tiếp 19/10/2026 9:00. Chưa thử chạy bù thật; chưa kiểm Ctrl+C trong Git Bash có tắt sạch tiến trình con không.
- `.gitattributes` mới ép file `.sh` dùng xuống dòng kiểu Linux (LF). Nếu git đổi sang CRLF thì bash báo lỗi `$'\r': command not found`.

## Tiếp theo

1. **Cắt theo đề mục** cho 669 văn bản có chữ nhưng không có Điều (387 còn hiệu lực). Thêm quy tắc vào `split_articles.py`, không thêm thư viện. *ĐỀ XUẤT — chờ người dùng đồng ý làm trước.*
2. **Đọc chữ từ file đính kèm**: 408 file cổng Bộ Tư pháp + 15 văn bản congbao. PDF → `pypdf`, lưu `text_origin = 'ocr'`. DOC/RTF → cần chọn công cụ (xem câu hỏi mở).
3. Tự tay so 5 văn bản trong database với bản gốc — điều kiện "Xong khi" của bước 2.

## Câu hỏi còn mở

- Ngưỡng của các bài kiểm pipeline (`app/pipeline/definitions.py`: lỗi ≤ 5% khi tải, ≤ 1% khi nạp, sitemap ≥ 90% danh sách đã biết) là tạm — chỉnh sau vài lần chạy thật.
- `\password` bên trong `psql -f` có hỏi mật khẩu trên Windows không? Chưa kiểm. Nếu không: chạy từng lệnh trong psql tương tác.
- **Chuyển PDF thành ảnh cho Tesseract** — Tesseract không đọc PDF trực tiếp. Lựa chọn: `pdftoppm` của poppler, hoặc thư viện Python (PyMuPDF có giấy phép AGPL — cần cân nhắc). Chưa kiểm.
- **Ragas dùng Claude làm giám khảo được không** — chưa kiểm (tài liệu chính chỉ có ví dụ OpenAI). Đọc mã nguồn ragas trước khi viết code đo.
- **Công cụ đọc .doc/RTF:** LibreOffice chạy không giao diện (một lệnh cho cả hai loại) hay cách khác? Chưa kiểm máy đã cài LibreOffice.
- **Mẹ có hay tư vấn chuyển nhượng nhà đất không?** Nếu có: thêm bộ lọc hẹp lấy bảng giá đất và lệ phí trước bạ của TP.HCM (gồm Bình Dương, Bà Rịa – Vũng Tàu cũ). Vai trò của bảng giá đất trong luật hiện hành: chưa kiểm.
- **Model embedding** cụ thể — đo ở bước Tìm kiếm.
- **Danh sách loại thuế cố định** cho bước hiểu câu hỏi (GTGT, TNDN, TNCN, hộ kinh doanh, hóa đơn, quản lý thuế/xử phạt…) — chốt cùng mẹ trước bước Trả lời.
- **Giấy phép BamiBERT:** ngoài BSD-3-Clause-Clear còn "Qualcomm responsible AI license" (https://www.qualcomm.com/site/responsible-ai-license) — chưa đọc. Đọc trước khi thử model này.
- **313 văn bản loại "Công văn" bị xếp `doc_group = 'UNKNOWN'`** (cổng không trả `docGroup`, cờ `isAdministrativeDocument` = false), cùng 49 "Sắc lệnh". Hệ quả: các công văn này sẽ không được gắn nhãn công văn. Sửa cách suy `doc_group` — chờ người dùng duyệt cùng các đề xuất về mô hình dữ liệu.
- **456 chunk dài hơn 8.000 ký tự**, dài nhất 473.833 ký tự (39/2018/TT-BTC) — giả định "một Điều là một đoạn tìm kiếm" vỡ ở các văn bản này; liên quan giới hạn đã biết của bộ tách (ngoặc kép không đóng).
- **Bảng lưu kết quả phân loại** để làm nhãn cho classifier: thêm cột vào `questions` hay bảng riêng? Quyết định khi viết migration ở bước Trả lời.
- **Ngưỡng đạt** cho mọi chỉ số trong `danh-gia.md` (tìm đúng Điều, OCR, câu trả lời) — đặt sau khi có mốc gốc.
- **`app/config.py` và `.env.example` còn cấu hình Claude cũ** (`claude-opus-5`, `claude-haiku-4-5`, ngân sách, hạn mức 5 tiếng) — thay bằng địa chỉ `llama-server` + tên model GGUF; giữ một mục cho giám khảo (tên model, giá) khi viết code bộ đo.
- **Hàm công khai để dọn checkpoint cũ** của `PostgresSaver` (mã nguồn có logic xoá theo thread và chỉ giữ checkpoint mới nhất) — chưa kiểm tên hàm.
- **Còn ~2 GB VRAM** khi `llama-server` chạy: embedding + reranker có vừa cùng lúc không, hay phải chạy embedding bằng CPU — đo ở bước Tìm kiếm.
- **Suy hiệu lực của văn bản hợp nhất** (90/107 để trống trạng thái) và cách dùng văn bản `HHL1P` khi tìm kiếm — xem `nguon-du-lieu.md`; làm ở bước Lịch sử sửa đổi.
- **Bật chế độ suy luận** (`-rea on`) có sửa được lỗi kiểu "áp nhầm khoản" không, và chậm thêm bao nhiêu — đo trên bộ câu hỏi thật.
- `pyproject.toml` khai báo `httpx` và `lxml` cho phần tải văn bản nhưng code chỉ dùng thư viện chuẩn → bỏ khỏi danh sách? `ruff` được cấu hình nhưng chưa cài trong `.venv`.
- Thêm `.vscode/` vào `.gitignore`?
- **Áp dụng thứ bậc vào bot** — 5 đề xuất ở cuối `thu-bac-van-ban.md` (xếp căn cứ theo cấp, nối công văn với văn bản nó hướng dẫn, nhãn "cần kiểm hiệu lực"…). Chờ người dùng duyệt từng điểm.
- **Link dự phòng cho mỗi văn bản:** bảng `documents` chỉ có một `source_url`. ĐỀ XUẤT: migration mới thêm cột `fallback_urls text[]`. Làm khi viết bộ đọc congbao/Cổng Chính phủ thành nguồn link.
- **gdt.gov.vn chặn script** (12/10/2026) — kiểm lại trước khi viết bộ tải công văn; nếu bị chặn hẳn thì cần phương án khác cho công văn.
- Trạng thái hiệu lực trên cổng Bộ Tư pháp có cập nhật theo quy tắc mới (văn bản hướng dẫn hết hiệu lực theo văn bản gốc, từ 01/07/2025) không? Chưa kiểm — đo trên Thông tư 80/2021 khi Luật Quản lý thuế 38/2019 hết hiệu lực 01/07/2026.
- Mô hình kinh doanh khi mở rộng — bàn khi tới lúc.

## Quyết định kiến trúc

Nội dung đầy đủ nằm trong `project-overview.md` và `architecture.md`. Ở đây chỉ ghi lại theo thời gian:

- 26–30/09/2026 (giai đoạn khảo sát) — PostgreSQL + pgvector, cắt theo Điều kèm vị trí khoản/điểm, quy trình cố định thay vì agent, Haiku cho việc rẻ + Opus viết câu trả lời, trần chi phí cứng.
- 02/10/2026 — Chỉ văn bản trung ương; chưa lấy phí, lệ phí; văn bản không có Điều cắt theo đề mục lớn nhất; văn bản JSON rỗng thì tải file đính kèm; mọi chữ từ PDF coi là OCR.
- 02/10/2026 — Tên thống nhất `taxassistant` cho package, database và user Postgres; app dùng user riêng chỉ có quyền trên database của mình.
- 08/10/2026 — Giai đoạn này dùng Claude API; giai đoạn sau tự host model (vLLM / SGLang) và lên VPS. Mọi lời gọi model nằm ở một chỗ.
- 18/10/2026 — Hiểu câu hỏi: mốc thời gian lấy bằng quy tắc, không dùng model. Loại thuế, loại câu hỏi tạm dùng Haiku, lưu kết quả, đủ nhãn thì thay bằng classifier trên embedding. Loại thuế chỉ ưu tiên, không lọc cứng. Thêm quy tắc bất biến số 12: thông tin quyết định đúng sai lấy tất định khi làm được.
- 21/10/2026 — **Điều phối luồng trả lời bằng LangGraph** + checkpointer Postgres; **hội thoại nhiều lượt** (mang sang ô có cấu trúc từ lượt trước). `answers` là bản ghi chính thức, checkpoint chỉ là trạng thái lúc chạy. Dùng `stream_mode`, `RetryPolicy`, `TimeoutPolicy`; không dùng agent dựng sẵn, LangSmith, vector store của LangChain (chỉ đọc làm bản đối chiếu).
- 21/10/2026 — **Tự host ngay trên laptop, bỏ Claude API trong app** (thay quyết định 08/10/2026). Chạy bằng `llama.cpp llama-server`; model đề xuất Qwen3.5-4B Q4_K_M. Lý do: học tự host, harness, deploy; đầu ra Claude không dùng được để huấn luyện (thêm quy tắc bất biến số 13). Bỏ ngân sách 300k và hạn mức 5 tiếng; trang chi phí thành trang hiệu năng. Claude chỉ còn làm giám khảo trong bộ đo.
- 18/10/2026 — Classifier thay bước phân loại tạm thời là encoder nhỏ fine-tune chạy trên máy (thử mmBERT-small, BamiBERT; mốc PhoBERT-base và embedding + logistic regression), để có bước tất định làm nền debug. Mỗi câu trả lời sai được xếp vào một loại: lấy sai thông tin / tìm sai / suy luận sai / bịa (`danh-gia.md`).
- 16/10/2026 — Lịch hằng tuần dùng lịch có sẵn của Dagster, không dùng Task Scheduler. Script chạy viết bằng bash thay cho PowerShell.
- 15/10/2026 — Giữ PostgreSQL (đã cân nhắc SQLite: dự phòng nếu thiếu pgvector). Điều phối pipeline bằng Dagster. Bản gốc bị nguồn sửa thì giữ bản cũ trong `history/`. Một văn bản lỗi không làm hỏng cả công đoạn (quy tắc bất biến số 11).
- 13/10/2026 — OCR dùng Tesseract tiếng Việt. Mọi công đoạn dùng model phải có guardrail và bài đo dựa trên nghiên cứu (`danh-gia.md`) trước khi đưa vào dùng.
- 12/10/2026 — Công văn cũ bắt buộc phải tìm thấy được, kể cả khi văn bản nó hướng dẫn đã hết hiệu lực.
- 11/10/2026 — Tài liệu theo bộ sáu file + `CLAUDE.md`; `quyet-dinh.md` được tách vào `project-overview.md` và `architecture.md`.

## Ghi chú cho phiên sau

- Dữ liệu trên đĩa (`data/raw/`, không commit): `moj/*.json` 3.159 file, `moj/sitemap.tsv`, `moj/files/` 408 file + `missing.txt` 95 dòng, `congbao/` 15 văn bản. Tổng khoảng 660 MB.
- Postgres trên máy này lưu dữ liệu ở `D:\Posgres Data`. Model HuggingFace tải về `D:\hf-cache` (biến `HF_HOME`). Ổ C còn ít chỗ — đừng tải gì lớn vào C.
- **pgvector trên máy này tự build từ mã nguồn** (19/10/2026): bản cài PostgreSQL 18 cho Windows không kèm pgvector. Cách làm: tải mã nguồn bản phát hành (không dùng git) → `vcvars64.bat` của Visual Studio Build Tools 2026 → `set PGROOT=C:\Program Files\PostgreSQL\18` → `nmake /F Makefile.win` (không cần admin) → chép `vector.dll`, `vector.control`, `sql\vector--*.sql` vào `lib\` và `share\extension\` của PostgreSQL (cần admin). **Nâng cấp PostgreSQL lên bản chính mới thì phải build lại.** Trên VPS (Linux) thì cài gói hoặc dùng image Docker có sẵn pgvector.
- GPU: RTX 3060 Laptop 6 GB VRAM — đủ cho embedding, không đủ cho model 7B trong vLLM.
- Người dùng tự commit; nhắc dùng `git add -A` để git nhận ra file đổi tên.

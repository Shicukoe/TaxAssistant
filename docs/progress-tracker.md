# Tiến độ

Cập nhật sau mỗi thay đổi đáng kể. Đây là nơi **duy nhất** ghi trạng thái; `ke-hoach.md` chỉ ghi kế hoạch.

Cập nhật: 16/10/2026

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
- `save_to_database.py` viết xong (chưa chạy — chờ database).
- Đo bộ lọc link (08/10/2026): không sót văn bản có "thuế" trong tiêu đề.
- Khảo sát văn bản địa phương (08/10/2026): giữ quyết định chỉ lấy trung ương.
- Tài liệu chuyển sang bộ sáu file theo mẫu, `CLAUDE.md` làm điểm vào (11/10/2026).
- Nghiên cứu thứ bậc văn bản, quy tắc áp dụng, vị trí công văn, đọc từ bản gốc Luật 64/2025, Luật 87/2025, Nghị định 78/2025, Nghị định 30/2020, Pháp lệnh Hợp nhất, Luật Quản lý thuế 108/2025 → `thu-bac-van-ban.md`. Kiểm nguồn thay thế → `nguon-du-lieu.md` (12/10/2026).
- **Pipeline dữ liệu tự động bằng Dagster** (15/10/2026): 5 công đoạn (danh sách → văn bản Bộ Tư pháp → file đính kèm → congbao; database), 6 bài kiểm chất lượng, log riêng từng công đoạn. Mỗi văn bản tự bắt lỗi; tự thử lại lỗi mạng; tải lại văn bản còn hiệu lực và giữ bản cũ trong `history/`; database chỉ nạp lại văn bản đổi (migration 002: `raw_sha256`, `parser_version`). Chạy: `bash scripts/run_pipeline.sh` (thêm `ui` để xem giao diện). Giải thích: `pipeline-du-lieu.md`.
- **Lần chạy thật đầu tiên** (15/10/2026, 69 phút): danh sách 3.168 văn bản, 0 mới. Tải lại 1.602 văn bản còn hiệu lực: 1.239 không đổi, **363 bị cổng sửa** (359 sửa phần nội dung, 4 sửa tiêu đề; trong 359 có 104 chỉ đổi HTML, còn lại đổi chữ, phần lớn là định dạng lại, có cả sửa lỗi chính tả như "a" → "ạ"). Bản cũ lưu ở `history/` (22 MB). 8 văn bản mới cổng trả HTTP 500 cả 3 lần → ghi lỗi, công đoạn chạy tiếp. File đính kèm, congbao: 0 lỗi. Database: lỗi mật khẩu như dự kiến.
- Khảo sát Unlimited-OCR (không chọn: ~6,7 GB không vừa GPU). Nghiên cứu phương pháp đánh giá (RAGAS, ALCE, RAGChecker, ARES, Magesh, OHRBench, BEIR…) → `danh-gia.md` (13/10/2026).

## Đang làm

- **Chờ người dùng** chạy lần lượt:
  1. `psql -U postgres -h 127.0.0.1 -f app/db/create_app_user.sql` — đặt mật khẩu cho `taxassistant`
  2. ghi mật khẩu vào `PGPASSWORD` trong `.env`
  3. `python -m app.db.setup_database` → `python -m app.db.check_database` (phải in `PASS`) → `python -m app.ingest.save_to_database`
  Đến lúc đó công đoạn `database_documents` của pipeline vẫn báo lỗi "password authentication failed" — đúng như dự kiến.
- Lịch chạy hằng tuần: dùng lịch của Dagster (thứ Hai 9:00), không dùng Task Scheduler. Chỉ chạy khi người dùng mở `bash scripts/run_pipeline.sh ui`; lỡ giờ thì chạy bù một lần lúc mở. Đã thử mở bằng Git Bash (16/10/2026): giao diện lên, lịch `RUNNING`, lần kế tiếp 19/10/2026 9:00. Chưa thử chạy bù thật; chưa kiểm Ctrl+C trong Git Bash có tắt sạch tiến trình con không.
- `.gitattributes` mới ép file `.sh` dùng xuống dòng kiểu Linux (LF). Nếu git đổi sang CRLF thì bash báo lỗi `$'\r': command not found`.

## Tiếp theo

1. **Cắt theo đề mục** cho 669 văn bản có chữ nhưng không có Điều (387 còn hiệu lực). Thêm quy tắc vào `split_articles.py`, không thêm thư viện. *ĐỀ XUẤT — chờ người dùng đồng ý làm trước.*
2. **Đọc chữ từ file đính kèm**: 408 file cổng Bộ Tư pháp + 15 văn bản congbao. PDF → `pypdf`, lưu `text_origin = 'ocr'`. DOC/RTF → cần chọn công cụ (xem câu hỏi mở).
3. Tự tay so 5 văn bản trong database với bản gốc — điều kiện "Xong khi" của bước 2.

## Câu hỏi còn mở

- Ngưỡng của các bài kiểm pipeline (`app/pipeline/definitions.py`: lỗi ≤ 5% khi tải, ≤ 1% khi nạp, sitemap ≥ 90% danh sách đã biết) là tạm — chỉnh sau vài lần chạy thật.
- **pgvector** đã có trên Postgres 18 Windows chưa? Biết khi chạy `create_app_user.sql`. Nếu thiếu: cài pgvector hoặc chạy Postgres trong Docker.
- `\password` bên trong `psql -f` có hỏi mật khẩu trên Windows không? Chưa kiểm. Nếu không: chạy từng lệnh trong psql tương tác.
- **Chuyển PDF thành ảnh cho Tesseract** — Tesseract không đọc PDF trực tiếp. Lựa chọn: `pdftoppm` của poppler, hoặc thư viện Python (PyMuPDF có giấy phép AGPL — cần cân nhắc). Chưa kiểm.
- **Chọn giám khảo AI cho bài đo câu trả lời** — không dùng Opus tự chấm. Haiku (rẻ, nhưng cùng họ Claude), model của hãng khác (thêm chi phí, thêm API key), hay model mở chạy trên máy (yếu)? Giám khảo nào cũng phải hiệu chỉnh với nhãn của mẹ. Ragas dùng được Claude không: chưa kiểm.
- **Công cụ đọc .doc/RTF:** LibreOffice chạy không giao diện (một lệnh cho cả hai loại) hay cách khác? Chưa kiểm máy đã cài LibreOffice.
- **Mẹ có hay tư vấn chuyển nhượng nhà đất không?** Nếu có: thêm bộ lọc hẹp lấy bảng giá đất và lệ phí trước bạ của TP.HCM (gồm Bình Dương, Bà Rịa – Vũng Tàu cũ). Vai trò của bảng giá đất trong luật hiện hành: chưa kiểm.
- **Model embedding** cụ thể — đo ở bước Tìm kiếm.
- **Ngưỡng đạt** cho mọi chỉ số trong `danh-gia.md` (tìm đúng Điều, OCR, câu trả lời) — đặt sau khi có mốc gốc.
- **Tên model và bảng giá Claude** trong `app/config.py` (`claude-opus-5`, `claude-haiku-4-5`, giá kiểm 28/09/2026) — kiểm lại trước bước Trả lời.
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
- 16/10/2026 — Lịch hằng tuần dùng lịch có sẵn của Dagster, không dùng Task Scheduler. Script chạy viết bằng bash thay cho PowerShell.
- 15/10/2026 — Giữ PostgreSQL (đã cân nhắc SQLite: dự phòng nếu thiếu pgvector). Điều phối pipeline bằng Dagster. Bản gốc bị nguồn sửa thì giữ bản cũ trong `history/`. Một văn bản lỗi không làm hỏng cả công đoạn (quy tắc bất biến số 11).
- 13/10/2026 — OCR dùng Tesseract tiếng Việt. Mọi công đoạn dùng model phải có guardrail và bài đo dựa trên nghiên cứu (`danh-gia.md`) trước khi đưa vào dùng.
- 12/10/2026 — Công văn cũ bắt buộc phải tìm thấy được, kể cả khi văn bản nó hướng dẫn đã hết hiệu lực.
- 11/10/2026 — Tài liệu theo bộ sáu file + `CLAUDE.md`; `quyet-dinh.md` được tách vào `project-overview.md` và `architecture.md`.

## Ghi chú cho phiên sau

- Dữ liệu trên đĩa (`data/raw/`, không commit): `moj/*.json` 3.159 file, `moj/sitemap.tsv`, `moj/files/` 408 file + `missing.txt` 95 dòng, `congbao/` 15 văn bản. Tổng khoảng 660 MB.
- Postgres trên máy này lưu dữ liệu ở `D:\Posgres Data`. Model HuggingFace tải về `D:\hf-cache` (biến `HF_HOME`). Ổ C còn ít chỗ — đừng tải gì lớn vào C.
- GPU: RTX 3060 Laptop 6 GB VRAM — đủ cho embedding, không đủ cho model 7B trong vLLM.
- Người dùng tự commit; nhắc dùng `git add -A` để git nhận ra file đổi tên.

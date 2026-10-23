# Kế hoạch xây dựng

Xây theo thứ tự dưới đây. Mỗi bước có mục **Xong khi** — chưa đạt thì chưa sang bước sau.
Trạng thái từng bước (đang làm, đã xong, đang chờ gì) ghi ở `progress-tracker.md`, không ghi ở đây.

Nhịp làm: 9–16 giờ/tuần. Tổng ước tính: 3–4 tháng.

**Không tải tay văn bản nào.** Bước 2 và 5 là script tự lấy danh sách, tự tải, tự lưu. Bạn chỉ chạy một lệnh rồi để máy chạy (lần đầu mất vài giờ vì cố ý chờ 2 giây giữa mỗi lần tải). Bị ngắt giữa chừng thì chạy lại, văn bản nào đã tải sẽ được bỏ qua. Từ bước 9, script tự chạy mỗi tuần. Việc tay duy nhất là kiểm tra: so vài văn bản với bản gốc và gom câu hỏi thật của mẹ.

---

## 1. Dựng database

**Làm:** cấu trúc 10 bảng, script tạo database, một bài tự kiểm.
**Lệnh:**
1. Một lần, bằng tài khoản quản trị: `psql -U postgres -h 127.0.0.1 -f app/db/create_app_user.sql` — tạo user riêng `taxassistant` (chỉ có quyền trên database của app) và cài 3 extension. Mật khẩu đặt cho `taxassistant` ghi vào `PGPASSWORD` trong `.env`.
2. `python -m app.db.setup_database` — tạo các bảng.
3. `python -m app.db.check_database`.
**Xong khi:** `python -m app.db.check_database` in ra `PASS`.

## 2. Lấy văn bản luật về — *2–3 tuần*

**Làm:** lấy danh sách văn bản từ sitemap vbpl.vn → tải từng văn bản từ cổng JSON Bộ Tư pháp → lưu bản gốc ra đĩa → tách Điều / khoản / điểm → tạo đoạn tìm kiếm theo từng Điều.
**Lệnh:**
1. `python -m app.ingest.download_moj_documents` — tải bản gốc ra `data/raw/moj/` (lần đầu khoảng 2 giờ).
2. `python -m app.ingest.download_from_congbao` — lấy từ congbao những văn bản còn hiệu lực mà cổng Bộ Tư pháp không có chữ, không có file.
3. `python -m app.ingest.save_to_database` — tách Điều/khoản/điểm (bằng `split_articles.py`) và nạp database.

**Gồm cả:** văn bản không chia Điều (cắt theo đề mục), chữ từ file DOC/RTF/PDF đính kèm.
**Xong khi:** mọi văn bản thuế trung ương tải được đã vào database (con số thật biết sau lần tải đầu; khoảng 3.200 ứng viên trước khi lọc), và tự tay so 5 văn bản với bản gốc thấy khớp. Có báo cáo OCR (CER, WER, CER bỏ dấu, độ chính xác chữ số) của Tesseract trên khoảng 20 văn bản — cách đo ở `danh-gia.md`.

## 3. Lịch sử sửa đổi — *1–2 tuần*

**Làm:** đọc chú thích của văn bản hợp nhất → ghi lại điều / khoản / cụm từ nào bị sửa, bởi văn bản nào, hiệu lực từ ngày nào.
**Xong khi:** hỏi "ngưỡng doanh thu miễn thuế của hộ kinh doanh năm 2025 và năm 2026" ra đúng 500 triệu và 1 tỷ.

## 4. Tìm kiếm — *1–2 tuần*

**Làm:** tìm theo từ khóa + tìm theo nghĩa, gộp kết quả. Chọn model embedding ở bước này. Nhận diện chỗ điều luật trỏ sang văn bản khác.
**Xong khi:** có bảng recall@5, MRR@10, nDCG@10 trên câu hỏi thật của mẹ (ít nhất 10 câu), đo riêng từ khóa / embedding / kết hợp — cách đo ở `danh-gia.md`.

## 5. Công văn — *2 tuần, làm song song với bước 3–4 được*

**Làm:** đọc danh sách công văn trên gdt.gov.vn → tải PDF → phân loại PDF có chữ / PDF scan → PDF scan thì OCR (chỉ để tìm).
**Xong khi:** tìm được công văn, kiểm chứng được chữ OCR không lọt ra phần trích dẫn, và bài đo OCR chạy lại trên mẫu công văn scan.

## 6. Trả lời — *2 tuần*

**Làm:** chạy model trên laptop bằng `llama-server` (Qwen3.5-4B 4-bit — ĐỀ XUẤT, chốt sau khi đo); lấy mốc thời gian bằng quy tắc (có test); phân loại loại thuế và loại câu hỏi bằng model trên máy (ép JSON schema), lưu kết quả để sau thay bằng classifier; viết câu trả lời, kiểm trích dẫn khớp với database; ghi token và thời gian chạy.
**Xong khi:** câu trả lời có trích dẫn đã kiểm; đo được thời gian trả lời và bộ nhớ GPU trên laptop; bộ 20 câu hỏi kiểm tra chạy được và cho ra báo cáo: RAGAS, citation recall/precision, nhãn của mẹ (đúng / ảo giác / chưa đủ), độ khớp giữa giám khảo và mẹ — giám khảo là Claude, cách đo ở `danh-gia.md`.

## 7. Giao diện cho mẹ — *1–2 tuần*

**Làm sớm** (chốt 22/10/2026): ngay sau bốn lớp giữ dữ liệu sạch (`architecture.md`, Dữ liệu), làm một web app FastAPI cho mạng nhà gồm **Tra cứu** và **Hỏi** (bản demo hiện tại). Phần còn lại của bước này (trang hiệu năng, lịch sử, nhãn đầy đủ) giữ nguyên chỗ.

**Làm:** web app (Hỏi + Tra cứu), lịch sử câu hỏi, trang hiệu năng, các nhãn bắt buộc (hết hiệu lực · công văn · OCR · không có căn cứ), dòng nhắc không nêu tên khách, cài mạng riêng để mẹ truy cập.
**Xong khi:** mẹ dùng được trên máy tính và điện thoại.

## 8. Đánh giá vi phạm và so sánh theo thời gian — *1–2 tuần*

**Làm:** câu trả lời dạng nếu–thì kèm cách xử lý; so sánh luật trước và sau khi sửa.
**Xong khi:** câu hỏi về xử phạt ra đủ mọi trường hợp, mỗi cách xử lý và mỗi thời hạn đều có căn cứ.
*Để gần cuối vì đây là phần rủi ro nhất — chỉ làm khi câu trả lời thường đã đáng tin.*

## 9. Tự động cập nhật — *1 tuần*

**Làm:** job hằng tuần lấy văn bản và công văn mới; cảnh báo khi cổng JSON lỗi. Pipeline Dagster (`scripts/run_pipeline.sh`) đã có từ 15/10/2026 — lịch hằng tuần của Dagster có từ 16/10/2026 — bước này còn: thêm công văn, cảnh báo.
**Xong khi:** job tự chạy mỗi tuần và bắt được văn bản mới.

---

## Trước khi mở cho nhiều người dùng

- Mẹ dùng thật ít nhất 4 tuần
- Bộ câu hỏi kiểm tra cho kết quả ổn định
- Model trên laptop trả lời trong thời gian chấp nhận được

Đạt cả ba mới sang giai đoạn sau: lên VPS có GPU (vLLM / SGLang), đặt lại ngân sách thuê GPU.

## Cải thiện model tự host (sau khi có mốc gốc)

Chỉ làm khi bộ đo chỉ ra điểm yếu cụ thể. Không dùng đầu ra của Claude làm dữ liệu (quy tắc bất biến số 13).

1. **SFT nhỏ:** câu trả lời mẹ sửa + câu model tự sinh rồi lọc bằng guardrail (rejection sampling, kiểu STaR).
2. **RLVR bằng GRPO:** phần thưởng là các guardrail tất định (trích dẫn khớp, số có căn cứ, dẫn đúng Điều theo nhãn, từ chối khi không có căn cứ, đúng khuôn).
3. **KTO / DPO** từ nút đúng/sai và bản sửa của mẹ.
4. **Công văn trả lời doanh nghiệp** làm bộ hỏi–đáp có sẵn căn cứ (gắn mốc thời gian vì có thể dẫn luật cũ).

GRPO trên 6 GB có lẽ chỉ làm được với model 0.8B–2B; 4B nhiều khả năng cần thuê GPU — chưa đo.

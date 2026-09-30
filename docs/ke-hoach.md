# Kế hoạch xây dựng

Xây theo thứ tự dưới đây. Mỗi bước có mục **Xong khi** — chưa đạt thì chưa sang bước sau.

Nhịp làm: 9–16 giờ/tuần. Tổng ước tính: 3–4 tháng.

---

## 1. Dựng database — *đang làm*

**Làm:** cấu trúc 10 bảng, script tạo database, một bài tự kiểm.
**Xong khi:** chạy `python -m app.selfcheck` in ra `PASS`.
**Đang chờ:** file `.env` có mật khẩu Postgres.

## 2. Lấy văn bản luật về — *2–3 tuần*

**Làm:** lấy danh sách văn bản từ sitemap vbpl.vn → tải từng văn bản từ cổng JSON Bộ Tư pháp → lưu bản gốc ra đĩa → tách Điều / khoản / điểm → tạo đoạn tìm kiếm theo từng Điều.
**Xong khi:** ít nhất 3.000 văn bản thuế đã vào database, và tự tay so 5 văn bản với bản gốc thấy khớp.

## 3. Lịch sử sửa đổi — *1–2 tuần*

**Làm:** đọc chú thích của văn bản hợp nhất → ghi lại điều / khoản / cụm từ nào bị sửa, bởi văn bản nào, hiệu lực từ ngày nào.
**Xong khi:** hỏi "ngưỡng doanh thu miễn thuế của hộ kinh doanh năm 2025 và năm 2026" ra đúng 500 triệu và 1 tỷ.

## 4. Tìm kiếm — *1–2 tuần*

**Làm:** tìm theo từ khóa + tìm theo nghĩa, gộp kết quả. Chọn model embedding ở bước này. Nhận diện chỗ điều luật trỏ sang văn bản khác.
**Xong khi:** thử 10 câu hỏi thật của mẹ, đo được bao nhiêu câu tìm ra đúng Điều trong 5 kết quả đầu.

## 5. Công văn — *2 tuần, làm song song với bước 3–4 được*

**Làm:** đọc danh sách công văn trên gdt.gov.vn → tải PDF → phân loại PDF có chữ / PDF scan → PDF scan thì OCR (chỉ để tìm).
**Xong khi:** tìm được công văn, và kiểm chứng được chữ OCR không lọt ra phần trích dẫn.

## 6. Trả lời — *2 tuần*

**Làm:** viết câu trả lời bằng Claude, kiểm trích dẫn khớp với database, giới hạn chi phí.
**Xong khi:** câu trả lời có trích dẫn đã kiểm; hết ngân sách thì app ngừng đúng lúc; bộ 20 câu hỏi kiểm tra chạy được.

## 7. Giao diện cho mẹ — *1–2 tuần*

**Làm:** web app, lịch sử câu hỏi, trang xem chi phí, các nhãn bắt buộc (hết hiệu lực · công văn · OCR · không có căn cứ), dòng nhắc không nêu tên khách, cài mạng riêng để mẹ truy cập.
**Xong khi:** mẹ dùng được trên máy tính và điện thoại.

## 8. Đánh giá vi phạm và so sánh theo thời gian — *1–2 tuần*

**Làm:** câu trả lời dạng nếu–thì kèm cách xử lý; so sánh luật trước và sau khi sửa.
**Xong khi:** câu hỏi về xử phạt ra đủ mọi trường hợp, mỗi cách xử lý và mỗi thời hạn đều có căn cứ.
*Để gần cuối vì đây là phần rủi ro nhất — chỉ làm khi câu trả lời thường đã đáng tin.*

## 9. Tự động cập nhật — *1 tuần*

**Làm:** job hằng tuần lấy văn bản và công văn mới; cảnh báo khi cổng JSON lỗi hoặc chi phí sắp hết.
**Xong khi:** job tự chạy mỗi tuần và bắt được văn bản mới.

---

## Trước khi mở cho nhiều người dùng

- Mẹ dùng thật ít nhất 4 tuần
- Bộ câu hỏi kiểm tra cho kết quả ổn định
- Chi phí thật nằm trong 300k/tháng

Đạt cả ba mới lên VPS và tăng ngân sách.

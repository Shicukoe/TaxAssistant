# Những gì đã quyết định

Tài liệu này ghi lại mọi lựa chọn đã chốt và lý do. Muốn đổi một lựa chọn thì sửa ở đây trước, rồi mới sửa code.

Cập nhật: 30/09/2026

---

## Sản phẩm

**Cho ai.** Mẹ — cựu kế toán, đang tư vấn thuế cho hộ kinh doanh và doanh nghiệp nhỏ ở TP.HCM. Bà có nghiệp vụ, nên bot không cần giải thích từ đầu. Hiện bà tra thông tin trên trang của cơ quan thuế — bot phải tiện và đáng tin hơn thế mới có lý do tồn tại.

**Phạm vi.** Chỉ pháp luật thuế, nhưng đủ mọi loại văn bản: luật, nghị định, nghị quyết, thông tư, quyết định, công văn. Chúng dẫn chiếu lẫn nhau nên thiếu một loại là trả lời hụt. Bao gồm cả văn bản về xử phạt vi phạm thuế và hóa đơn.

**Ngoài phạm vi.** Luật ngoài lĩnh vực thuế. Làm thay người dùng (nộp hồ sơ, xuất tờ khai). Công văn của Cục Thuế các tỉnh (có thể thêm sau).

**Quy mô.** Giai đoạn đầu chỉ mẹ dùng. Mục tiêu sau đó: 50 tài khoản, cùng lúc 1–5 người hỏi.

---

## Bot trả lời thế nào

Đây là phần quan trọng nhất — nó quyết định bot có đáng tin hay không.

**Trích dẫn nguyên văn.** Mỗi câu trả lời kèm: tên văn bản, điều/khoản/điểm, đoạn trích đúng từng chữ, link bản gốc. Trích dẫn phải khớp với đoạn văn bản đã lưu trong database trước khi hiện ra — model không được tự nghĩ ra số điều, số khoản.

**Biết hiệu lực.** Mỗi căn cứ có nhãn: còn hiệu lực / hết hiệu lực / hết hiệu lực một phần.

**Trả lời theo mốc thời gian.** Hỏi "năm 2025 quy định thế nào" thì trả lời theo năm 2025, không theo hôm nay. So sánh được trước và sau khi luật đổi.

**Phân biệt văn bản luật và công văn.** Công văn là hướng dẫn của cơ quan thuế, không phải văn bản quy phạm pháp luật. Bot dẫn văn bản luật trước, công văn sau, và gắn nhãn rõ.

**Tính toán.** Hiện từng bước, mỗi bước kèm căn cứ, để mẹ kiểm lại được. Không đưa ra con số trần trụi.

**Đánh giá vi phạm.** Bot trả lời theo dạng *"nếu … thì …"*: nếu tình huống là A thì thuộc quy định X, mức phạt Y, cách xử lý Z. Mỗi cách xử lý và mỗi thời hạn đều phải có căn cứ riêng. Bot **không kết luận** khách đã vi phạm hay chưa — bot chịu trách nhiệm về căn cứ, mẹ chịu trách nhiệm xác định sự thật.
Trên giao diện, điều kiện và cách xử lý phải nằm cùng một khối, và bot phải trình bày đủ mọi trường hợp, không tự chọn một.
*Lý do:* khi bot sai, người chịu hậu quả là khách của mẹ — người không hề dùng hệ thống.

**Không tìm thấy căn cứ.** Trả lời ở mức định hướng chung, nói rõ "không có căn cứ trích dẫn", gợi ý nơi tra. Không bịa trích dẫn.

**Điều luật trỏ sang chỗ khác.** Bot không tự mở thêm văn bản được trỏ tới, để giữ chi phí. Nhưng nếu thiếu phần đó làm điều luật không hiểu được, bot bắt buộc thêm một câu kiểu: *"nội dung quyết định nằm ở Điều 7 Luật số 109/2025/QH15 — cần tra thêm"*. Khi phân vân thì cứ thêm — thừa một dòng rẻ hơn thiếu.

**Công văn scan (PDF ảnh).** Chữ đọc bằng OCR chỉ dùng để tìm kiếm. Khi căn cứ là công văn scan, bot chỉ đưa số hiệu + link PDF, không trích chữ OCR — vì OCR có thể đọc "8.000.000" thành "3.000.000".

---

## Dữ liệu

**Lập trường.** Chỉ lấy dữ liệu công khai và không vi phạm quy định nào đã công bố. Không xin phép, không chờ giấy phép. Nghiên cứu cho thấy trong lĩnh vực này không có nguồn nào cấp phép rõ ràng — chi tiết ở [nguon-du-lieu.md](nguon-du-lieu.md).

**Nguồn dùng.**
- Cổng dữ liệu JSON của Bộ Tư pháp — nguồn chính cho văn bản luật: đủ nội dung, có trạng thái hiệu lực.
- congbao.chinhphu.vn — nguồn dự phòng.
- gdt.gov.vn — công văn của Cục Thuế trung ương.

**Không dùng.**
- thuvienphapluat.vn, luatvietnam.vn — điều khoản của họ cấm thu thập tự động. Mua tài khoản VIP cũng không được, vì chính thỏa thuận thành viên là thứ cấm.
- Các bộ dữ liệu có sẵn trên mạng — tự xây từ đầu.

**Công văn.** Lấy toàn bộ công văn trung ương lấy được, kể cả bản scan (qua OCR, chỉ để tìm). Công văn quá cũ không có file đính kèm — chấp nhận không có.

**Cách lưu.** Ba lớp:
- văn bản hợp nhất — để đọc, và phần chú thích cuối trang cho biết điều nào bị sửa khi nào
- văn bản gốc
- văn bản sửa đổi

Luôn lưu bản gốc ra đĩa trước khi xử lý.

**Cắt văn bản theo Điều.** Mỗi đoạn dùng để tìm kiếm là một Điều trọn vẹn, kèm vị trí từng khoản/điểm bên trong để trích dẫn được chi tiết.
*Lý do:* cắt nhỏ tới điểm thì nhiều điểm đứng một mình vô nghĩa. Ví dụ điểm a khoản 4 Điều 13 Nghị định 125/2020 chỉ nói "nộp hồ sơ trễ 61–90 ngày" — mức phạt 8–15 triệu nằm ở câu đầu của khoản.

**Cập nhật** hằng tuần, tự động.

---

## Kỹ thuật

| | Chọn | Vì sao |
|---|---|---|
| Ngôn ngữ | **Python + FastAPI**, giao diện HTML/CSS/JS thuần render từ server | Phần nặng (đọc PDF, OCR, chạy model trên GPU) đều mạnh nhất ở Python. Một ngôn ngữ, một chương trình, không cần bước build |
| Database | **PostgreSQL** ngay từ đầu | Không phải chuyển database khi lên server |
| Tìm kiếm | **Kết hợp** tìm theo từ khóa (bỏ dấu tiếng Việt) + tìm theo nghĩa (vector) | Mỗi cách bắt được những câu cách kia bỏ sót |
| Lưu vector | **pgvector** trong Postgres | Không cần thêm Qdrant — Postgres đã làm được |
| Embedding | Chạy trên **GPU RTX 3060** của laptop | Miễn phí. Model cụ thể chọn sau khi đo thử |
| Model AI | **Claude Haiku 4.5** cho việc rẻ (phân loại câu hỏi, lọc kết quả), **Claude Opus 5** để viết câu trả lời | Chỉ trả giá cao ở bước người dùng thật sự đọc |
| Giao diện | Web, tốt trên máy tính, dùng được trên điện thoại | Mẹ dùng máy tính là chính |

---

## Chi phí

- **Ngân sách:** 300.000đ/tháng cho tất cả. Khi mở rộng có thể tăng lên 500–700k, nhưng chỉ sau khi đã thấy kết quả với ít người dùng.
- **Ước tính:** khoảng 1.700đ/câu hỏi → khoảng 170 câu/tháng. Đủ cho mẹ, **không đủ** cho 50 người dùng thường xuyên.
- **Trần cứng:** app tự cộng chi phí từ mỗi lần gọi API; hết ngân sách tháng thì ngừng trả lời. Thêm giới hạn số câu trong mỗi 5 tiếng.
- Không đọc được "% còn lại" từ tài khoản Claude — gói Claude Pro và API là hai đường tính tiền riêng.

---

## Chạy ở đâu, ai vào được

- **Giai đoạn đầu:** chạy trên laptop. Mẹ truy cập qua mạng riêng (VPN kiểu Tailscale) — không mở gì ra internet, chưa cần đăng nhập, chưa cần domain.
- **Khi đủ tốt:** chuyển lên VPS + mua domain. VPS thường không có GPU → lúc đó chạy embedding bằng CPU, hoặc đổi sang dịch vụ embedding qua API và tính lại vector cho toàn bộ dữ liệu (việc một buổi).
- **Dữ liệu của khách:** được gửi lên API, vì mẹ sẽ hỏi không nêu tên khách. Giao diện có một dòng nhắc việc này.

---

## Người làm và thời gian

Một mình, 9–16 giờ/tuần, không deadline. **Ưu tiên số một: làm xong dữ liệu trước.**

---

## Chưa chốt

- Mô hình kinh doanh khi mở rộng — bàn khi tới lúc.
- Model embedding cụ thể — đo rồi chọn.

---

## Rủi ro đã biết

1. **Cổng JSON của Bộ Tư pháp có thể tắt bất cứ lúc nào** — nó không có tài liệu công bố. → Luôn lưu bản gốc, có nguồn dự phòng.
2. **Lịch sử sửa đổi không đầy đủ.** Thông tin "điều nào bị sửa khi nào" chỉ có trong chú thích văn bản hợp nhất, và rất không đều — có văn bản 0 chú thích, có văn bản 123. Văn bản chưa được hợp nhất thì không biết lịch sử.
3. **Luật bị sửa tới từng cụm từ.** Một nghị định đổi "500 triệu đồng" thành "01 tỷ đồng" ở 18 chỗ cùng lúc. Theo dõi lịch sử theo điều/khoản chỉ là gần đúng.
4. **Lấy công văn lần đầu dễ hỏng** (467 trang, chuyển trang phụ thuộc phiên). Cập nhật hằng tuần thì dễ.
5. **Mẹ có thể đọc "cách xử lý" như kết luận**, dù bot trình bày dạng nếu–thì. Chỉ biết khi bà dùng thật.

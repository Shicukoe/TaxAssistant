# TaxAssistant — Tổng quan sản phẩm

Cập nhật: 11/10/2026. Muốn đổi một điều ở đây thì sửa file này trước, rồi mới sửa code.

## Tổng quan

Chatbot tra cứu pháp luật thuế Việt Nam. Người dùng hỏi bằng tiếng Việt, bot trả lời kèm **căn cứ trích nguyên văn** từ văn bản luật đã lưu, biết văn bản nào còn hiệu lực, và trả lời được theo một mốc thời gian trong quá khứ.

**Cho ai.** Mẹ — cựu kế toán, đang tư vấn thuế cho hộ kinh doanh và doanh nghiệp nhỏ ở TP.HCM. Bà có nghiệp vụ, nên bot không cần giải thích từ đầu. Hiện bà tra trên trang của cơ quan thuế — bot phải tiện và đáng tin hơn thế mới có lý do tồn tại.

**Người chịu hậu quả khi bot sai** là khách của mẹ — người không hề dùng hệ thống. Vì vậy độ đúng của căn cứ quan trọng hơn mọi tính năng khác.

**Quy mô.** Giai đoạn đầu chỉ mẹ dùng. Mục tiêu sau đó: 50 tài khoản, cùng lúc 1–5 người hỏi.

**Người làm.** Một mình, 9–16 giờ/tuần, không deadline. Ưu tiên số một: làm xong dữ liệu trước.

## Mục tiêu

1. **Không có trích dẫn sai.** 100% trích dẫn hiện ra khớp từng chữ với đoạn văn bản đã lưu trong database. Trích dẫn không khớp thì không hiện. Đo thêm citation recall/precision và tỷ lệ ảo giác — xem `danh-gia.md`.
2. **Tìm đúng Điều.** Với bộ câu hỏi thật của mẹ, đo được tỷ lệ câu có Điều đúng nằm trong 5 kết quả đầu (ngưỡng đạt chưa chốt — xem progress-tracker). Cách đo: recall@5, MRR@10, nDCG@10 trong `danh-gia.md`.
3. **Đúng theo thời gian.** Hỏi "ngưỡng doanh thu miễn thuế của hộ kinh doanh năm 2025 và năm 2026" ra đúng 500 triệu và 1 tỷ.
4. **Trong ngân sách.** Tổng chi phí ≤ 300.000đ/tháng; hết ngân sách thì app tự ngừng trả lời.
5. **Được dùng thật.** Mẹ dùng thật ít nhất 4 tuần.

## Luồng sử dụng chính

1. Mẹ mở web app trên máy tính (hoặc điện thoại) qua mạng riêng — không cần đăng nhập ở giai đoạn đầu.
2. Mẹ gõ câu hỏi. Dưới ô nhập có dòng nhắc: không nêu tên khách.
3. Nếu câu hỏi nhắc tới một năm/ngày, hệ thống lấy đó làm **mốc thời gian**; không nhắc thì mốc là hôm nay.
4. Hệ thống phân loại câu hỏi (loại thuế, mốc thời gian), tìm các Điều liên quan bằng cả từ khóa lẫn nghĩa, lọc theo hiệu lực tại mốc, xếp văn bản luật trước công văn.
5. Claude viết câu trả lời từ các Điều tìm được.
6. Mọi trích dẫn trong câu trả lời được so với chữ đã lưu; trích dẫn không khớp bị bỏ.
7. Mẹ đọc câu trả lời: từng bước lập luận, mỗi bước kèm căn cứ (tên văn bản, Điều/khoản/điểm, đoạn trích nguyên văn, link bản gốc) và nhãn bắt buộc.
8. Mẹ xem lại các câu đã hỏi trong lịch sử, và xem chi phí tháng này ở trang chi phí.

## Tính năng

### Trả lời có căn cứ

- **Trích dẫn nguyên văn.** Mỗi câu trả lời kèm: tên văn bản, điều/khoản/điểm, đoạn trích đúng từng chữ, link bản gốc. Trích dẫn phải khớp với đoạn đã lưu trong database trước khi hiện ra — model không được tự nghĩ ra số điều, số khoản.
- **Phân biệt văn bản luật và công văn.** Công văn là hướng dẫn của cơ quan thuế, không phải văn bản quy phạm pháp luật. Dẫn văn bản luật trước, công văn sau, gắn nhãn rõ.
- **Công văn scan (PDF ảnh).** Chữ đọc bằng OCR chỉ dùng để tìm. Khi căn cứ là công văn scan, chỉ đưa số hiệu + link PDF, không trích chữ OCR — OCR có thể đọc "8.000.000" thành "3.000.000".
- **Không tìm thấy căn cứ.** Trả lời ở mức định hướng chung, nói rõ "không có căn cứ trích dẫn", gợi ý nơi tra. Không bịa trích dẫn.
- **Điều luật trỏ sang chỗ khác.** Không tự mở thêm văn bản được trỏ tới (giữ chi phí). Nhưng nếu thiếu phần đó làm điều luật không hiểu được, bắt buộc thêm một câu kiểu *"nội dung quyết định nằm ở Điều 7 Luật số 109/2025/QH15 — cần tra thêm"*. Phân vân thì cứ thêm — thừa một dòng rẻ hơn thiếu.

### Thời gian và hiệu lực

- **Nhãn hiệu lực** cho mỗi căn cứ: còn hiệu lực / hết hiệu lực / hết hiệu lực một phần.
- **Trả lời theo mốc thời gian.** Hỏi "năm 2025 quy định thế nào" thì trả lời theo năm 2025, không theo hôm nay.
- **So sánh trước và sau** khi luật đổi.

### Tính toán và đánh giá vi phạm

- **Tính toán** hiện từng bước, mỗi bước kèm căn cứ, để mẹ kiểm lại được. Không đưa con số trần trụi.
- **Đánh giá vi phạm** theo dạng *"nếu … thì …"*: nếu tình huống là A thì thuộc quy định X, mức phạt Y, cách xử lý Z. Mỗi cách xử lý và mỗi thời hạn có căn cứ riêng. Bot **không kết luận** khách đã vi phạm hay chưa — bot chịu trách nhiệm về căn cứ, mẹ chịu trách nhiệm xác định sự thật. Trình bày đủ mọi trường hợp, không tự chọn một.

### Chi phí và vận hành

- Tự cộng chi phí từ mỗi lần gọi API; hết ngân sách tháng thì ngừng trả lời; giới hạn số câu trong mỗi 5 tiếng.
- Trang xem chi phí.
- Tự động lấy văn bản và công văn mới mỗi tuần; cảnh báo khi cổng dữ liệu lỗi hoặc chi phí sắp hết.

## Phạm vi

### Trong phạm vi

- Pháp luật thuế, đủ mọi loại văn bản: luật, nghị định, nghị quyết, thông tư, quyết định, công văn — chúng dẫn chiếu lẫn nhau nên thiếu một loại là trả lời hụt. Gồm cả xử phạt vi phạm thuế và hóa đơn.
- Chỉ văn bản **trung ương** (chốt 02/10/2026).
- Công văn của Cục Thuế trung ương (gdt.gov.vn), kể cả bản scan (chỉ để tìm).
- **Công văn cũ bắt buộc phải tìm thấy được** (chốt 12/10/2026), kể cả khi văn bản nó hướng dẫn đã hết hiệu lực. Lý do: kỳ thuế cũ áp dụng văn bản có hiệu lực lúc đó, cơ quan thuế truy thu được tới 10 năm, và cần đặt công văn cũ cạnh quy định mới để so. Chi tiết ở `thu-bac-van-ban.md`.
- Web app cho một người dùng, truy cập qua mạng riêng.

### Ngoài phạm vi

- Luật ngoài lĩnh vực thuế.
- Văn bản của UBND, HĐND các tỉnh (chốt 02/10/2026) — đo 08/10/2026: hơn một nửa là "cho thuê đất/nhà", không phải thuế. Bảng giá tính thuế riêng của từng tỉnh vì vậy chưa có.
- Phí, lệ phí (chốt 02/10/2026) — kể cả lệ phí trước bạ. Nếu mẹ hay hỏi thì thêm một từ khóa rồi tải lại.
- Công văn của Cục Thuế các tỉnh (có thể thêm sau).
- Làm thay người dùng: nộp hồ sơ, xuất tờ khai.
- Kết luận một tình huống thật là vi phạm.
- Đăng nhập, nhiều tài khoản, domain, mở ra internet công cộng — chỉ làm sau khi đạt tiêu chí thành công.
- Tự host model AI — giai đoạn sau (xem architecture.md, mục Chạy ở đâu).
- Dùng dữ liệu của thuvienphapluat.vn, luatvietnam.vn, hoặc bộ dữ liệu có sẵn trên mạng.

## Tiêu chí thành công

Trước khi mở cho nhiều người dùng, phải đạt cả ba:

1. Mẹ dùng thật ít nhất 4 tuần.
2. Bộ câu hỏi kiểm tra (20 câu, lấy từ câu hỏi thật của mẹ) cho kết quả ổn định giữa các lần chạy.
3. Chi phí thật nằm trong 300.000đ/tháng.

Từng bước xây dựng có tiêu chí "Xong khi" riêng trong `ke-hoach.md`.

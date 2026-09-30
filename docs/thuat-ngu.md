# Thuật ngữ

Những từ dưới đây có nghĩa chính xác trong project này. Đọc trước khi sửa code xử lý văn bản luật.

---

## Người

**Người tra cứu** — người dùng hệ thống (hiện là mẹ). Có nghiệp vụ kế toán – thuế, không cần giải thích từ đầu.

**Người được tư vấn** — khách của mẹ: hộ kinh doanh, doanh nghiệp nhỏ. Không dùng hệ thống, nhưng **là người chịu hậu quả khi bot sai**.

## Văn bản

**Văn bản quy phạm pháp luật (VBQPPL)** — Luật, Nghị định, Nghị quyết, Thông tư… Là **căn cứ pháp lý**. Danh sách đầy đủ ở Luật 64/2025 Điều 4.
Lưu ý: *Quyết định của Bộ trưởng* **không** nằm trong danh sách đó. Một văn bản có phải VBQPPL hay không tùy **ai ban hành**, không tùy tên loại.

**Công văn** — hướng dẫn hoặc trả lời của cơ quan thuế. **Không phải VBQPPL**, nhưng kế toán dùng rất nhiều. Không có Điều — là văn xuôi, bên trong trích lại Điều của văn bản khác. Trích dẫn công văn bằng **số hiệu**, không bằng điều/khoản.

**Văn bản hợp nhất** — bản gộp văn bản gốc với mọi lần sửa đổi, đọc liền mạch. Phần **chú thích cuối trang** cho biết đoạn nào bị sửa, bởi văn bản nào, hiệu lực từ ngày nào — đây là nguồn duy nhất cho lịch sử sửa đổi.

**Văn bản sửa đổi, bổ sung** — sửa một phần văn bản khác. **Văn bản thay thế** — làm văn bản khác hết hiệu lực hoàn toàn.

## Hiệu lực

**Còn hiệu lực** · **Hết hiệu lực** · **Hết hiệu lực một phần** — trạng thái cuối rất phổ biến: một số điều/khoản đã bị bỏ hoặc sửa, phần còn lại vẫn áp dụng.

**Mốc thời gian** — thời điểm câu hỏi hướng tới. Mặc định là hôm nay. Mọi câu trả lời đều gắn với một mốc.

**Đơn vị bị sửa nhỏ nhất là cụm từ**, không phải khoản hay điểm. Ví dụ: một nghị định đổi "500 triệu đồng" thành "01 tỷ đồng" ở 18 chỗ trong văn bản khác cùng lúc.

## Cấu trúc điều luật

**Điều / Khoản / Điểm** — ba cấp chia nhỏ trong một văn bản. **Chỉ Điều có tên**; khoản và điểm chỉ có số (điểm có thể là `a`, `b` hoặc `5.3`).

**Câu dẫn** — câu đầu của một khoản, đứng trước danh sách điểm. Thường chứa nội dung quyết định (mức phạt, điều kiện). Tách điểm khỏi câu dẫn là mất nghĩa.

## Câu trả lời

**Trích dẫn** — đoạn văn bản dẫn ra làm căn cứ. Phải **đúng từng chữ** với văn bản gốc, kèm tên văn bản + điều/khoản + link. Trích dẫn sai chữ là lỗi nghiêm trọng, không phải lỗi nhỏ.

**Căn cứ** — tập các trích dẫn đỡ cho một câu trả lời.

**Không có căn cứ** — khi kho dữ liệu không có văn bản phù hợp. Bot trả lời định hướng chung và nói rõ điều đó. Không bịa trích dẫn.

**Tính toán có căn cứ** — hiện từng bước tính, mỗi bước kèm căn cứ. Con số không có bước tính không phải câu trả lời hợp lệ.

**Đánh giá có điều kiện** — cách trả lời câu hỏi về vi phạm: *"nếu A thì thuộc quy định X, mức Y"*. Bot không khẳng định tình huống thật là A. Bot chịu trách nhiệm về căn cứ; người tra cứu chịu trách nhiệm xác định sự thật.

**Cách xử lý đề xuất** — việc cần làm, gắn với **một trường hợp cụ thể** trong đánh giá có điều kiện, và phải có căn cứ riêng. Đề xuất không có căn cứ thì chỉ được hiện như lưu ý chung.

**Câu tham chiếu** — một câu bot thêm vào khi điều luật trỏ sang văn bản khác mà thiếu phần đó thì không hiểu được: *"nội dung quyết định nằm ở Điều 7 Luật số 109/2025/QH15 — cần tra thêm"*.

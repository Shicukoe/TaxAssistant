# Nguồn dữ liệu

Lấy luật từ đâu, lấy được gì, giới hạn ở đâu. Mọi điều dưới đây đã được kiểm tra trực tiếp ngày 26–28/09/2026.

---

## Kết luận

Trong lĩnh vực này **không có nguồn nào cấp phép rõ ràng** cho việc dùng lại dữ liệu:
- Các trang nhà nước **không có điều khoản sử dụng** nào — im lặng, không phải cho phép.
- Hai trang thương mại lớn **cấm rõ ràng**.

Vì vậy project chọn: **chỉ lấy dữ liệu công khai và không vi phạm quy định nào đã công bố.**

---

## Nguồn đang dùng

### Cổng JSON của Bộ Tư pháp — nguồn chính

`https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/{uuid}`

- **Có:** toàn văn sạch (không phải scan), ngày hiệu lực, trạng thái hiệu lực (ví dụ `HHL1P` = hết hiệu lực một phần), loại văn bản, cờ phân biệt văn bản hành chính.
- **Không có:** quan hệ giữa các văn bản. Các trường `provisionTree`, `references`, `documentRelatedList` luôn rỗng.
- **Rủi ro:** không có tài liệu công bố; tên máy chủ có chữ "bientap" (biên tập) → có thể là cổng nội bộ và tắt bất cứ lúc nào. Không có robots.txt, không có điều khoản.

Danh sách văn bản lấy từ `vbpl.vn/sitemap.xml`: 37 file, khoảng 172.000 văn bản, trong đó khoảng 7.000 liên quan thuế.
- Phải dùng User-Agent kiểu trình duyệt, nếu không bị chặn (lỗi 403).
- Không truy cập `/api/` và `/Pages/` của vbpl.vn — robots.txt cấm.

### congbao.chinhphu.vn — nguồn dự phòng

- **Có:** PDF có chữ + file Word, RSS văn bản mới, văn bản hợp nhất.
- **Bắt buộc:** ghi rõ nguồn "congbao.chinhphu.vn".
- **Hạn chế:** đăng chậm 16–69 ngày so với ngày ban hành; ít thông tin hiệu lực.

### gdt.gov.vn — công văn

- **Có:** danh sách "Hệ thống văn bản" 467 trang × 30 dòng ≈ 14.000 văn bản (1983 → nay), ước khoảng **6.000–11.000 công văn**. Danh sách mặc định không có CAPTCHA.
- **Bắt buộc:** ghi rõ nguồn "https://www.gdt.gov.vn".
- **Hạn chế:**
  - Chuyển trang bằng POST, phụ thuộc phiên truy cập → không có link cố định cho từng trang.
  - Form tìm kiếm có CAPTCHA — **không dùng, không vượt**.
- **Chất lượng file:**
  - văn bản gần đây: PDF có chữ
  - khoảng năm 2019: PDF scan, cần OCR
  - văn bản rất cũ: không có file đính kèm
- **Cập nhật:** mỗi tháng khoảng 25–35 công văn mới, đều nằm ở trang 1–2 → cập nhật hằng tuần rất rẻ.

---

## Nguồn không dùng

| Nguồn | Lý do |
|---|---|
| **thuvienphapluat.vn** | Thỏa thuận thành viên cấm "sử dụng phần mềm hoặc bất kỳ công cụ tự động nào để truy cập, thu thập hoặc tải xuống nội dung", và cấm dùng dữ liệu "để phát triển thành… hệ thống lưu trữ và tra cứu khác" |
| **luatvietnam.vn** | Cấm bot/crawler, cấm tự xây cơ sở dữ liệu, cấm "huấn luyện mô hình trí tuệ nhân tạo" khi chưa có văn bản đồng ý |
| **Dữ liệu có sẵn trên Hugging Face** | Giấy phép do người đăng tự gán, không phải do nguồn cấp. Một bộ còn lấy từ thuvienphapluat trái điều khoản. Owner chọn tự xây |
| **Trang Cục Thuế các tỉnh** | Mỗi trang chỉ hiện 10 văn bản, không phân trang; cấu trúc không đồng nhất giữa các tỉnh |
| **vietlaw.quochoi.vn** | PDF là ảnh scan |
| **mof.gov.vn** | Trang dựng hoàn toàn bằng JavaScript, không lấy được gì |

---

## Cần biết khi viết code thu thập

- **Cấu trúc điều luật** nằm trong HTML dạng class `prov-article` (Điều), `prov-clause` (khoản), `prov-item` (điểm). Các thẻ **xếp ngang hàng, không lồng nhau** → quan hệ cha–con phải suy theo thứ tự xuất hiện.
- **Markup không đầy đủ.** Thông tư 18/2026 có 9 Điều nhưng chỉ 4 Điều được đánh dấu → luôn cần regex dự phòng.
- **Điểm không chỉ là a, b, c** — có cả "5.3", "5.4".
- **Chú thích văn bản hợp nhất** có hai dạng chính:
  - *"Điểm này được sửa đổi, bổ sung theo quy định tại điểm a khoản 6 Điều 1 của Nghị định số 310/2025/NĐ-CP, có hiệu lực kể từ ngày 16 tháng 01 năm 2026."*
  - *"Cụm từ "500 triệu đồng" được thay thế bởi cụm từ "01 tỷ đồng" theo quy định tại khoản 1, Điều 1 của Nghị định số 141/2026/NĐ-CP…"*
- **Công văn không có Điều** — là văn xuôi. Cần cách cắt và cách trích dẫn riêng (theo số hiệu công văn).
- **"Quyết định của Bộ trưởng" không phải văn bản quy phạm pháp luật** (Luật 64/2025 Điều 4 không liệt kê). Tính quy phạm tùy người ban hành, không tùy tên loại văn bản.
- **Trang Cục Thuế tỉnh:** tên thư viện trong URL phải viết HOA (`DANANG`, không phải `danang`). Link trên chính trang đó viết thường nên bị 404.
- **robots.txt** của mọi trang gdt.gov.vn chỉ chặn `coccocbot`, không có Crawl-delay.

---

## Vì sao cắt văn bản theo Điều

**Luật chỉ bắt buộc Điều phải có tên** (Luật 64/2025 Điều 7 khoản 2). Khoản và điểm chỉ có số, nên đứng riêng thì không biết nói về chủ đề gì.

**Khoản và điểm thường không đứng riêng được.** Hai ví dụ thật:

> Nghị định 125/2020, Điều 13 khoản 4: *"Phạt tiền từ 8.000.000 đồng đến 15.000.000 đồng đối với một trong các hành vi sau đây: a) Nộp hồ sơ khai thuế quá thời hạn quy định từ 61 ngày đến 90 ngày; …"*

→ Tách riêng điểm a thì **mất mức phạt**.

> Nghị định 68/2026, Điều 4 khoản 2: *"Cá nhân kinh doanh có doanh thu năm trên mức doanh thu quy định tại khoản 1 Điều này thực hiện nộp thuế…"*

→ Tách riêng khoản 2 thì **mất con số**. Và con số ở khoản 1 vừa đổi từ 500 triệu lên 1 tỷ từ 01/01/2026 — nghĩa là ý nghĩa của khoản 2 đã đổi dù khoản 2 không bị sửa một chữ nào.

**Các hệ thống tra cứu luật tiếng Việt hiện có đều cắt theo Điều.** Chưa có ai đo so sánh cắt theo Điều với cắt theo khoản hay điểm.

---

## Chưa kiểm chứng

- Tốc độ gọi tối đa mà các trang cho phép (mới thử từng request lẻ)
- Mốc năm chính xác công văn chuyển từ PDF scan sang PDF có chữ
- Chất lượng OCR tiếng Việt trên công văn scan

# Nguồn dữ liệu

Lấy luật từ đâu, lấy được gì, giới hạn ở đâu. Mọi điều dưới đây đã được kiểm tra trực tiếp ngày 26–28/09/2026, phần số liệu tải về đo ngày 02/10/2026.

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

- **Có:** toàn văn dạng HTML (với khoảng 78% văn bản — xem bên dưới), ngày hiệu lực, trạng thái hiệu lực (ví dụ `HHL1P` = hết hiệu lực một phần), loại văn bản, lĩnh vực (`documentFields`, văn bản cũ để trống), cờ phân biệt văn bản hành chính.
- **Không có:** quan hệ giữa các văn bản. Các trường `provisionTree`, `references`, `documentRelatedList` luôn rỗng.
- **File đính kèm:** `https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/minio/buckets/vbpl/{id}/{tên file}/download`, tên file lấy từ `documentContentFileName` (PDF) và `documentContentFileDocName` (DOC). Đây là đường trang vbpl.vn dùng để hiện file. Cùng máy chủ với cổng JSON, không thuộc `/api/` của vbpl.vn.

**Kết quả lần tải đầu (02/10/2026), chỉ văn bản trung ương:**

| | Số văn bản |
|---|---|
| Ứng viên lọc theo link | 3.167 |
| Tải được | 3.159 — 8 văn bản cũ (1980–2003) cổng luôn trả lỗi 500 |
| Là văn bản thuế (lọc theo tiêu đề có dấu) | 2.864 — 1.424 còn hiệu lực |
| Có chữ trong JSON | 2.246 (78%) |
| **JSON rỗng** (chỉ khung HTML trống) | **618 (22%)** — 315 còn hiệu lực; gồm 82/107 văn bản hợp nhất và 276 công văn |
| — cứu được bằng file đính kèm | 408 |
| — mất hẳn (không có file, hoặc máy chủ trả 404) | 210 — 195 đã hết hiệu lực. 15 văn bản còn lại (14 văn bản hợp nhất 2014–2024, trong đó 03/VBHN-VPQH Luật Thuế TNCN, + Thông tư 31/2017/TT-BTC) **đã lấy đủ từ congbao** — 8 có file .doc, 7 chỉ có PDF |

**Bộ lọc link có bỏ sót không** (đo 08/10/2026): sitemap trung ương có 46.898 văn bản, 3.168 qua bộ lọc link. Lấy ngẫu nhiên 150 văn bản bị loại, tải JSON kiểm: 3 văn bản (2%) có lĩnh vực "Quản lý thuế, phí và lệ phí" nhưng nội dung đều là phí/lệ phí — loại đã quyết định chưa lấy. Không văn bản nào có chữ "thuế" trong tiêu đề bị sót. Link vbpl.vn chứa nguyên tiêu đề, không bị cắt ngắn (dài nhất 1.177 ký tự), nên lọc theo link không làm rơi văn bản có "thuế" trong tên.

**Cổng sửa văn bản sau khi đăng** (đo 15/10/2026): tải lại 20 văn bản còn hiệu lực đã lưu ngày 02/10 → 4 văn bản đổi nội dung HTML, 8 văn bản có trường nào đó đổi (phần lớn là `reviewStatus`), không văn bản nào đổi trạng thái hiệu lực. Có văn bản chỉ thêm markup (chữ y nguyên), có văn bản sửa chữ thật — Nghị định 41/2022/NĐ-CP khác 16 dòng ("KTH" → "KTTH", dấu ":" → ";"…). Vì vậy pipeline tải lại văn bản còn hiệu lực mỗi lần chạy và giữ bản cũ trong `history/`.

**Trạng thái hiệu lực không lọc cứng được** (đo 22/10/2026 trên database): 90/107 văn bản hợp nhất có trạng thái **để trống** — gồm cả 113/VBHN-VPQH (hợp nhất Luật Thuế TNDN năm 2026). Luật gốc đang dùng thường mang `HHL1P` (hết hiệu lực một phần) chứ không phải `CHL` — ví dụ Luật Thuế TNDN 67/2025/QH15 sau khi bị Luật 09/2026/QH16 sửa. Lọc `eff_status_code = 'CHL'` loại mất đúng các văn bản cần nhất. Hiệu lực của văn bản hợp nhất phải suy từ văn bản được hợp nhất và từ chú thích; việc này thuộc bước Lịch sử sửa đổi.

File 404 chủ yếu là .doc của văn bản trước 2003; danh sách ở `data/raw/moj/files/missing.txt`, bộ tải không thử lại. 8 văn bản cổng luôn trả lỗi 500 thì vẫn được thử lại mỗi lần (rẻ, và biết đâu cổng sửa).

**Định dạng file đính kèm:** RTF mang đuôi .doc, .doc kiểu cũ (Word 97), PDF.
**PDF có chữ chưa chắc là chữ gốc.** Nhiều PDF là bản scan đã được OCR sẵn — chữ sai kiểu "XẢ HỘI", "QUYÉT ĐỊNH", "THÔNG Tư". Một số PDF khác là ảnh thuần, không có chữ.

**Văn bản không chia Điều:** 669 văn bản có chữ nhưng không có "Điều" nào — chủ yếu thông tư thập niên 1990–2000, chia theo Phần / Mục / I. / 1. (419 văn bản có đề mục kiểu này, 250 không có). 387 văn bản trong số đó vẫn ghi "còn hiệu lực".
- **Rủi ro:** không có tài liệu công bố; tên máy chủ có chữ "bientap" (biên tập) → có thể là cổng nội bộ và tắt bất cứ lúc nào. Không có robots.txt, không có điều khoản.

Danh sách văn bản lấy từ `vbpl.vn/sitemap.xml`: 37 file, khoảng 172.000 văn bản, trong đó khoảng 7.000 liên quan thuế.
- Phải dùng User-Agent kiểu trình duyệt, nếu không bị chặn (lỗi 403).
- Không truy cập `/api/` và `/Pages/` của vbpl.vn — robots.txt cấm.

### congbao.chinhphu.vn — nguồn dự phòng

- **Có:** PDF có chữ + file Word, RSS văn bản mới, văn bản hợp nhất.
- **Bắt buộc:** ghi rõ nguồn "congbao.chinhphu.vn".
- **Hạn chế:** đăng chậm 16–69 ngày so với ngày ban hành; ít thông tin hiệu lực.
- **Tìm văn bản:** `POST https://api-searchcongbao.chinhphu.vn/search/van-ban` với JSON `{"filters":{},"page":1,"page_size":20,"query":"<số hiệu>"}` — chính API mà ô tìm kiếm trên trang dùng, không CAPTCHA. robots.txt của congbao.chinhphu.vn cho phép tất cả. Kết quả có sẵn link tải PDF/DOC/DOCX (`danh_sach_tep_van_ban`).
- **Bẫy khi khớp với cổng Bộ Tư pháp:**
  - Số hiệu văn bản hợp nhất lặp lại mỗi năm → phải so cả ngày ban hành.
  - Ngày ban hành có thể lệch 1 ngày giữa hai nguồn.
  - Cổng Bộ Tư pháp đôi khi ghi thiếu năm trong số hiệu ("31/TT-BTC" thay vì "31/2017/TT-BTC").
  - Văn bản hợp nhất dài bị chia qua nhiều số công báo → nhiều cặp PDF/DOC.
  - Link cũ viết đuôi dính liền không có dấu chấm (`...-03vbhn-bctpdf`); trường `file_extension` có lúc là rác.

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
- **15/10/2026:** kể cả trang chủ `https://www.gdt.gov.vn/` cũng chỉ trả 244 byte khi gọi bằng script — trang đang chặn truy cập tự động. Bộ tải công văn phải giải quyết việc này trước.
- **12/10/2026:** gọi `https://gdt.gov.vn/robots.txt` bằng script bị tường lửa trả trang "Request Rejected". Trước đây gọi được. Phải thử lại trước khi viết bộ tải công văn — có thể trang đã chặn truy cập tự động.

### Nguồn thay thế khi nguồn chính hỏng

Kiểm 12/10/2026. Có hai mức dùng khác nhau:
- **Lấy chữ về** (tải tự động) — chỉ khi robots.txt cho phép và không có điều khoản cấm.
- **Chỉ đặt link** để người dùng tự mở đối chiếu — được với mọi trang chính thống, vì không tải gì về.

| Trang | Là gì | robots.txt | Dùng được ở mức |
|---|---|---|---|
| vbpl.vn + cổng JSON Bộ Tư pháp | Cơ sở dữ liệu quốc gia về pháp luật (Luật 64/2025 Điều 66) | Cấm `/api/`, `/Pages/` | Lấy chữ — nguồn chính |
| congbao.chinhphu.vn | Công báo điện tử — nơi bắt buộc đăng toàn văn văn bản quy phạm pháp luật trung ương (Nghị định 78/2025 Điều 7) | Cho phép tất cả | Lấy chữ — nguồn dự phòng, đã dùng |
| vanban.chinhphu.vn | "Hệ thống văn bản" của Cổng thông tin Chính phủ | Cho phép tất cả | Lấy chữ được theo robots.txt; **chưa kiểm** cấu trúc trang và điều khoản |
| phapluat.gov.vn | "Cổng Pháp luật quốc gia" | Cấm `/api/`, `/_next/`, `/admin/`. Sitemap trỏ sang tên miền lạ `phapluat-dev.biznext.vn` | **Chưa kiểm** điều khoản; sitemap lạ → chưa tin để tải tự động |
| quochoi.vn | Văn bản của Quốc hội | Trang bắt chạy JavaScript đặt cookie mới vào được | Chỉ đặt link |
| mof.gov.vn | Cổng Bộ Tài chính | Không có robots.txt (trả về trang web) | Chỉ đặt link |
| gdt.gov.vn | Công văn Cục Thuế | Bị tường lửa chặn khi gọi bằng script (xem trên) | Đặt link; lấy chữ phải kiểm lại |

**Nguyên tắc:** chữ bot trích luôn lấy từ **bản gốc đã lưu trên đĩa**, không đọc trực tiếp từ trang web lúc trả lời. Vì vậy trang nguồn sập không làm hỏng trích dẫn — chỉ làm hỏng link. Mỗi văn bản nên có **nhiều link**: link chính (vbpl.vn) và link dự phòng (congbao, Cổng Chính phủ). Bảng `documents` hiện chỉ có một cột `source_url` → cần thêm chỗ chứa link dự phòng (đề xuất ở `progress-tracker.md`).

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
- **Markup không đầy đủ.** Thông tư 18/2026 có 9 Điều nhưng chỉ 4 Điều được đánh dấu → luôn cần regex dự phòng. Đo trên toàn bộ văn bản thuế có Điều: 1.170 markup đủ, 77 markup thiếu, 326 không có markup.
- **Điểm không chỉ là a, b, c** — có cả "5.3", "5.4".
- **Kết quả bộ tách** (`app/ingest/split_articles.py`, đo 02/10/2026 trên 1.562 văn bản có Điều, lấy markup làm đáp án): bắt được 99,8% Điều, 98,1% khoản, 98,0% điểm. Ra 12.324 Điều, 54.052 khoản/điểm. Phần trượt chủ yếu là markup đánh nhầm (ví dụ "Nơi nhận" bị đánh dấu là Điều).
- **Những thứ bộ tách phải xử lý** — đều gặp trong dữ liệu thật:
  - Văn bản sửa đổi trích nguyên Điều mới trong ngoặc kép “…”, nhiều dòng, có khi nhiều Điều → dòng "1.", "Điều 10." bên trong không được mở khoản/Điều mới.
  - Ngoặc gõ lẫn "“…\"" → '"' cũng tính là dấu đóng.
  - Văn bản cũ đánh số "2)", "2-", "b/", "b.", và không có điểm "đ" (a, b, c, d, e).
  - 53 văn bản có số Điều quay lại từ đầu: quyết định ban hành kèm theo quy chế → Điều của phần kèm theo lưu dạng "QC1.5".
- **Giới hạn đã biết của bộ tách:** khi một ngoặc kép trong văn bản sửa đổi không bao giờ đóng, các Điều phía sau bị nhập vào Điều đang mở (ví dụ TT 39/2018 chỉ ra 1 Điều). Chữ không mất, chỉ không tách riêng. 365 Điều dài hơn 2.000 từ — phần lớn là "Điều 1. Sửa đổi, bổ sung…" của văn bản sửa đổi → bước Tìm kiếm phải xử lý đoạn dài.
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

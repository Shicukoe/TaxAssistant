# Giao diện

Bố cục và màu đã chốt (mục Phong cách, Màu); phần còn lại làm ở bước Giao diện cho mẹ (`ke-hoach.md`). Những gì dưới đây là ràng buộc đã biết; chỗ ghi ĐỀ XUẤT là gợi ý, chưa phải quyết định.

## Người dùng và thiết bị

- Mẹ: kế toán có kinh nghiệm, đọc nhiều chữ, cần kiểm lại căn cứ. Giao diện phục vụ **đọc và đối chiếu**. Có hỏi nối tiếp trong một cuộc hội thoại (chốt 21/10/2026), nhưng mỗi câu trả lời vẫn đủ căn cứ như câu hỏi đầu, không trả lời kiểu tán gẫu.
- Máy tính là chính; điện thoại phải dùng được.
- Toàn bộ chữ trên giao diện bằng tiếng Việt.

## Phong cách

**Chốt 23/10/2026 (người dùng: "vị trí các component giống ChatGPT cho dễ dùng"; thay khuôn agent-chat-ui chốt trước đó cùng ngày):**
- **Thanh bên trái** (260px; điện thoại: ẩn, mở bằng nút ☰; máy tính: thu gọn được): trên cùng tên **Tax Assistant** + nút thu gọn; nút **Cuộc hội thoại mới**; **Gần đây** — danh sách cuộc hội thoại (câu hỏi đầu tiên làm tên); dưới cùng: **Hiệu năng** và nút **sáng / tối**. Thanh bên cùng tông với nền (không còn khối xanh đậm), như ChatGPT.
- **Thanh trên cùng** mọi trang: nút thanh bên, **hai tab Hỏi đáp · Tra cứu** (chế độ chính của app, như chỗ chọn model của ChatGPT).
- **Hỏi đáp:** cột giữa rộng tối đa 768px. Màn hình trống: lời chào + **ô nhập nằm giữa màn hình** + câu hỏi mẫu bên dưới; hỏi câu đầu thì ô nhập xuống **dính đáy**. Câu hỏi: bong bóng bo tròn bên phải, nền xanh nhạt. Câu trả lời: chữ chạy hết cột, **không avatar**; dưới câu trả lời có nút **Sao chép** (kết luận + căn cứ). Đang chờ: ba chấm + tên bước đang chạy. Các bước của luồng trả lời thu gọn trong một khối ("Đã kiểm qua 8 bước"), debug nằm trong đó, chỉ trên laptop.
- **Ô nhập:** khung bo tròn lớn, nút gửi tròn màu nhấn ở góc phải; Enter gửi, Shift+Enter xuống dòng. Dòng nhắc nhỏ dưới ô nhập: "Không nêu tên khách hàng · luôn đối chiếu căn cứ".
- **Tra cứu, Hiệu năng, trang văn bản:** cùng thanh trên, cùng cột giữa, cùng thẻ và màu — hai tab nhìn như một app.
- **Sáng / tối:** mặc định theo cài đặt của máy (`prefers-color-scheme`); bấm nút thì nhớ lựa chọn trên máy đó (localStorage — chỉ là tiện ích, mất cũng không sao). Đặt chế độ trước khi trang hiện để không chớp trắng.
- **Màu chủ đạo vẫn là xanh dương** ở cả hai chế độ. Chế độ tối theo phong cách **synthwave**: nền chàm đêm, xanh dương điện, viền / vòng sáng xanh neon khi focus; hồng chỉ dùng ở logo. Chữ thân 17px; tương phản chữ thường ≥ 4,5:1 ở cả hai chế độ.

## Màu

Mọi màu khai báo một lần dưới dạng biến CSS (`app/web/static/app.css`): chế độ sáng trên `:root`, chế độ tối ghi đè trong `[data-theme="dark"]`; thành phần chỉ dùng biến.

| Vai trò | Biến CSS | Sáng | Tối (synthwave) |
|---|---|---|---|
| Nền trang | `--bg-base` | `#ffffff` | `#0e0b24` |
| Nền khối, ô nhập | `--bg-surface` | `#ffffff` | `#17133a` |
| Nền phụ (trích dẫn, bảng) | `--bg-subtle` | `#f4f7fd` | `#1d1847` |
| Nền thanh bên | `--bg-sidebar` | `#f3f6fc` | `#0a081b` |
| Nền mục thanh bên khi rê chuột / đang chọn | `--bg-sidebar-hover` | `#e3ebfa` | `#221c52` |
| Chữ chính | `--text-primary` | `#14213d` | `#ece9ff` |
| Chữ phụ | `--text-muted` | `#5b6782` | `#a59fd0` |
| Nhấn (nút, tab đang chọn) | `--accent-primary` | `#1f5fd1` | `#2f6bff` |
| Nhấn đậm (hover) | `--accent-strong` | `#1747a6` | `#4d82ff` |
| Link | `--link` | `#1f5fd1` | `#8ab8ff` |
| Nền nhấn nhạt | `--accent-soft` | `#e8effd` | `#1f2766` |
| Bong bóng câu hỏi | `--bubble-user` | `#e8effd` | `#232d75` |
| Viền | `--border-default` | `#dbe3f0` | `#2e2866` |
| Vòng sáng focus | `--focus-ring` | `#bcd2fb` | `#36e2ff` (xanh neon) |
| Nhãn hết hiệu lực / không có căn cứ | `--label-expired`, `--label-no-basis` | `#b42318` | `#ff8a98` |
| Nhãn công văn | `--label-guidance` | `#8a5300` | `#ffc46b` |
| Nhãn OCR | `--label-ocr` | `#5a4fb3` | `#c0b2ff` |
| Nhãn cần kiểm | `--label-check` | `#9a5b00` | `#ffb35c` |

## Chữ

| Vai trò | Font | Biến |
|---|---|---|
| Chữ giao diện và văn bản | chưa chốt — **bắt buộc hiển thị đúng dấu tiếng Việt** | `--font-sans` |
| Trích dẫn nguyên văn | chưa chốt — phải phân biệt rõ với lời bot | `--font-quote` |

## Bo góc

Chưa chốt. Một thang duy nhất cho cả app, khai báo bằng biến CSS.

## Thư viện thành phần

Không dùng. HTML/CSS/JS thuần, template Jinja2 render từ server, không bước build (xem `architecture.md`).

## Màn hình và bố cục

Ba màn hình:

1. **Hỏi – đáp:** các lượt hỏi–đáp của cuộc hội thoại đang mở, xếp từ trên xuống; ô nhập + dòng nhắc bên dưới; mỗi câu trả lời có danh sách căn cứ riêng; nút **cuộc hội thoại mới** (bỏ ngữ cảnh lượt trước). Khi câu hỏi nối tiếp mang ngữ cảnh từ lượt trước, hiện rõ ngữ cảnh đã dùng (ví dụ "hộ kinh doanh · thuế GTGT · mốc 2026").
2. **Lịch sử:** các cuộc hội thoại đã có, mở lại được từng lượt hỏi–đáp.
3. **Hiệu năng** (thay trang chi phí từ 21/10/2026): thời gian trả lời, số câu đã hỏi, bộ nhớ GPU. Làm 23/10/2026 (`/hieu-nang`): số câu (tổng, hôm nay, 7 ngày); thời gian trả lời trung vị và chậm nhất 10% theo nhánh (chào hỏi / khái niệm / câu hỏi thường) — đo từ lúc nhận câu hỏi tới lúc lưu, câu trả lời trước 23/10/2026 không có số này; 20 câu gần nhất; bộ nhớ GPU; tốc độ đọc và sinh trung bình của model viết. Ai trong mạng nhà cũng xem được — không có chữ câu trả lời, chỉ có câu hỏi.
**Bản demo đầu (22/10/2026, `bash scripts/run_web_demo.sh`):** có Hỏi (hội thoại nhiều lượt, nút cuộc hội thoại mới, tiến độ từng bước) và Tra cứu (danh sách + trang văn bản + bản gốc). Chưa có: nút báo sai, lọc theo loại thuế (danh sách loại thuế chưa chốt). **Khung debug** (kết quả từng bước, như bản terminal) chỉ hiện khi mở trên chính laptop (`127.0.0.1`), máy khác trong mạng không thấy.

4. **Tra cứu** (chốt 22/10/2026) — đọc thẳng, không qua model:
   - **Danh sách:** lọc theo thứ bậc văn bản (`thu-bac-van-ban.md`), loại thuế, hiệu lực tại một ngày, có ô tìm theo số hiệu / chữ. Văn bản hợp nhất đứng trước văn bản gốc.
   - **Trang văn bản:** dựng thành HTML từ database, một khuôn cho mọi văn bản: mục lục Điều/khoản, mỗi Điều/khoản có địa chỉ riêng (link trích dẫn trỏ vào đây), nhãn hiệu lực và chất lượng, văn bản sửa đổi / hợp nhất liên quan, **link tải bản gốc** (PDF/Word) và link trang nguồn. Văn bản scan: chỉ file gốc + nhãn OCR, không hiện chữ OCR như chữ thật. Cần PDF thì in từ trình duyệt.
   - **Nút báo sai** trên trang văn bản → danh sách chờ xem tay.

Bố cục: xem Phong cách (chốt 23/10/2026).

## Thành phần bắt buộc

Những thứ này là yêu cầu sản phẩm, không được bỏ:

- **Dòng nhắc** dưới ô nhập: không nêu tên khách.
- **Mốc thời gian** mà câu trả lời áp dụng, hiện rõ ở đầu câu trả lời.
- **Khối căn cứ:** tên văn bản, Điều/khoản/điểm, đoạn trích nguyên văn, link bản gốc.
- **Nhãn:** hết hiệu lực · hết hiệu lực một phần · **cần kiểm hiệu lực** (cổng ghi còn hiệu lực nhưng văn bản cũ, chốt 22/10/2026) · công văn · OCR (chỉ số hiệu + link, không trích) · không có căn cứ · **chưa kiểm chất lượng / đang cách ly** (trang tra cứu).
- **Khối nếu–thì** cho câu hỏi vi phạm: điều kiện và cách xử lý nằm **cùng một khối**, đủ mọi trường hợp.
- **Thông báo khi model trên laptop không chạy** (chưa bật `llama-server`, hết bộ nhớ GPU) thay cho câu trả lời.

## Icon

Chốt 23/10/2026: icon SVG nội tuyến (không thư viện, không phông icon), nét 2px, theo màu chữ (`currentColor`). Mục có chữ thì icon đứng trước chữ. Nút chỉ có icon (gửi, thanh bên, sáng/tối, sao chép) phải có `aria-label` và `title`. Nhãn hiệu lực / căn cứ luôn có chữ — không để icon đứng một mình.

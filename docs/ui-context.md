# Giao diện

Phần lớn **chưa chốt** — làm ở bước Giao diện cho mẹ (`ke-hoach.md`). Những gì dưới đây là ràng buộc đã biết; chỗ ghi ĐỀ XUẤT là gợi ý, chưa phải quyết định.

## Người dùng và thiết bị

- Mẹ: kế toán có kinh nghiệm, đọc nhiều chữ, cần kiểm lại căn cứ. Giao diện phục vụ **đọc và đối chiếu**, không phải trò chuyện.
- Máy tính là chính; điện thoại phải dùng được.
- Toàn bộ chữ trên giao diện bằng tiếng Việt.

## Phong cách

**ĐỀ XUẤT:** nền sáng, tương phản cao, chữ to vừa phải (chữ thân bài khoảng 17–18px), ít màu. Màu chỉ dùng để phân biệt nhãn, không để trang trí. Lý do: đọc văn bản luật dài trong thời gian dài.

## Màu

Mọi màu khai báo một lần dưới dạng biến CSS trên `:root`; thành phần chỉ dùng biến, không viết mã màu trực tiếp. Giá trị: **chưa chốt**.

| Vai trò | Biến CSS | Giá trị |
|---|---|---|
| Nền trang | `--bg-base` | chưa chốt |
| Nền khối | `--bg-surface` | chưa chốt |
| Chữ chính | `--text-primary` | chưa chốt |
| Chữ phụ | `--text-muted` | chưa chốt |
| Nhấn (nút, link) | `--accent-primary` | chưa chốt |
| Viền | `--border-default` | chưa chốt |
| Nhãn hết hiệu lực | `--label-expired` | chưa chốt |
| Nhãn công văn | `--label-guidance` | chưa chốt |
| Nhãn OCR | `--label-ocr` | chưa chốt |
| Nhãn không có căn cứ | `--label-no-basis` | chưa chốt |

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

1. **Hỏi – đáp:** ô nhập câu hỏi + dòng nhắc bên dưới; câu trả lời; danh sách căn cứ.
2. **Lịch sử:** các câu đã hỏi, mở lại được câu trả lời cũ.
3. **Chi phí:** đã dùng bao nhiêu trong tháng, còn bao nhiêu, còn bao nhiêu câu trong 5 tiếng.

Bố cục cụ thể: chưa chốt.

## Thành phần bắt buộc

Những thứ này là yêu cầu sản phẩm, không được bỏ:

- **Dòng nhắc** dưới ô nhập: không nêu tên khách.
- **Mốc thời gian** mà câu trả lời áp dụng, hiện rõ ở đầu câu trả lời.
- **Khối căn cứ:** tên văn bản, Điều/khoản/điểm, đoạn trích nguyên văn, link bản gốc.
- **Nhãn:** hết hiệu lực · hết hiệu lực một phần · công văn · OCR (chỉ số hiệu + link, không trích) · không có căn cứ.
- **Khối nếu–thì** cho câu hỏi vi phạm: điều kiện và cách xử lý nằm **cùng một khối**, đủ mọi trường hợp.
- **Thông báo hết ngân sách** khi app ngừng trả lời.

## Icon

Chưa chốt. Nếu dùng thì nhãn vẫn phải có chữ — không để icon đứng một mình.

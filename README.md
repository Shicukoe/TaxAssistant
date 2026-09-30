# Trợ lý thuế

Chatbot giúp tra cứu pháp luật thuế Việt Nam. Mọi câu trả lời kèm **trích dẫn nguyên văn** từ văn bản gốc, biết văn bản **còn hay hết hiệu lực**, và trả lời được **theo mốc thời gian** ("năm 2025 quy định thế nào").

Người dùng đầu tiên: mẹ — cựu kế toán, tư vấn thuế cho hộ kinh doanh và doanh nghiệp nhỏ.

---

## Đọc gì

| File | Nội dung |
|---|---|
| [docs/quyet-dinh.md](docs/quyet-dinh.md) | Những gì đã chốt và vì sao. **Đọc đầu tiên.** |
| [docs/ke-hoach.md](docs/ke-hoach.md) | Xây theo thứ tự nào, đang ở bước nào |
| [docs/nguon-du-lieu.md](docs/nguon-du-lieu.md) | Lấy luật từ đâu, lấy được gì, giới hạn ở đâu |
| [docs/thuat-ngu.md](docs/thuat-ngu.md) | Các từ có nghĩa chính xác trong project. Đọc trước khi sửa code xử lý văn bản luật |

---

## Chạy

```bash
cp .env.example .env        # rồi điền PGPASSWORD
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .      # Windows
# source .venv/bin/activate && pip install -e .     # Linux / macOS

./.venv/Scripts/python.exe -m app.db.migrate        # tạo database + các bảng
./.venv/Scripts/python.exe -m app.selfcheck         # phải in ra PASS
```

Cấu trúc database nằm ở [app/db/migrations/001_init.sql](app/db/migrations/001_init.sql), mỗi bảng có chú thích giải thích vì sao nó tồn tại.

---

## Năm quy tắc không được phá

Đây là lý do project có giá trị. Muốn đổi thì sửa [docs/quyet-dinh.md](docs/quyet-dinh.md) trước.

1. **Trích dẫn phải khớp đúng đoạn văn bản đã lưu trong database.** Model không được tự nghĩ ra số điều, số khoản.
2. **Chữ đọc bằng OCR chỉ dùng để tìm kiếm**, không bao giờ hiện ra như trích dẫn.
3. **Không vượt CAPTCHA** của trang Cục Thuế. Chỉ đọc danh sách công khai.
4. **Luôn lưu bản gốc ra đĩa trước khi xử lý.** Nguồn chính có thể tắt bất cứ lúc nào.
5. **Ghi rõ nguồn** khi dùng nội dung từ congbao.chinhphu.vn và gdt.gov.vn — hai trang này yêu cầu.

---

## Tiến độ

- ⏳ Dựng database — code xong, chờ `.env`
- ⬜ Lấy văn bản luật về
- ⬜ Lịch sử sửa đổi
- ⬜ Tìm kiếm
- ⬜ Công văn
- ⬜ Trả lời
- ⬜ Giao diện cho mẹ
- ⬜ Đánh giá vi phạm và so sánh theo thời gian
- ⬜ Tự động cập nhật

Chi tiết từng bước ở [docs/ke-hoach.md](docs/ke-hoach.md).

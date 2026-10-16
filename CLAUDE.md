# TaxAssistant — đọc trước khi làm

Chatbot tra cứu pháp luật thuế Việt Nam cho mẹ. Trước khi viết code hoặc đưa ra quyết định kiến trúc, đọc theo thứ tự:

1. `docs/project-overview.md` — làm gì, cho ai, phạm vi, thế nào là xong
2. `docs/architecture.md` — công nghệ, thư mục nào lo việc gì, dữ liệu nằm đâu, các quy tắc không bao giờ được phá
3. `docs/ui-context.md` — giao diện (phần lớn chưa chốt)
4. `docs/code-standards.md` — cách viết code trong dự án này
5. `docs/ai-workflow-rules.md` — cách làm việc, và những việc **không được tự làm**
6. `docs/progress-tracker.md` — đang ở đâu, việc tiếp theo, câu hỏi còn mở

Đọc thêm khi đụng tới:

- `docs/ke-hoach.md` — kế hoạch 9 bước, mỗi bước có "Xong khi"
- `docs/nguon-du-lieu.md` — kết quả khảo sát nguồn dữ liệu, bẫy của từng cổng, số liệu đo được
- `docs/danh-gia.md` — guardrail và bài đo cho từng công đoạn dùng model, chỉ số lấy từ nghiên cứu (đọc trước khi đụng tới OCR, tìm kiếm, prompt)
- `docs/pipeline-du-lieu.md` — Dagster là gì, các công đoạn, bài kiểm chất lượng, cách chạy, xem lỗi ở đâu
- `docs/thu-bac-van-ban.md` — thứ bậc văn bản, quy tắc chọn văn bản khi mâu thuẫn, vị trí của công văn (dẫn điều luật cụ thể)
- `docs/thuat-ngu.md` — nghĩa chính xác của từ chuyên môn (Điều/khoản/điểm, công văn, văn bản hợp nhất…)

Sau mỗi thay đổi đáng kể: cập nhật `docs/progress-tracker.md`.

Thay đổi nào làm lệch kiến trúc, phạm vi hay quy tắc code: đề xuất với người dùng, chờ đồng ý, sửa file tài liệu tương ứng **trước**, rồi mới sửa code.

# Quy tắc làm việc cho AI

Viết cho AI lập trình (Claude Code hoặc tương tự). Đây là quy tắc, không phải gợi ý.

## Cách làm

- Xây theo `ke-hoach.md`, từng bước một. Mỗi bước có "Xong khi" — chưa đạt thì không sang bước sau.
- **Người dùng quyết định, AI đề xuất.** Mọi lựa chọn chưa được người dùng chốt phải ghi là **ĐỀ XUẤT**, kèm ưu nhược điểm và một khuyến nghị. Chỉ khi người dùng đồng ý mới ghi vào tài liệu như quyết định, kèm ngày chốt.
- Làm đúng thứ tài liệu mô tả. Không tự nghĩ ra hành vi sản phẩm.

## Giới hạn phạm vi

- Làm một việc một lúc. Ưu tiên bước nhỏ kiểm chứng được hơn thay đổi lớn đoán trước.
- Không gộp các ranh giới khác nhau vào một thay đổi: tải dữ liệu, schema database, tìm kiếm, gọi model, giao diện là năm vùng riêng.
- Không viết code "để sau dùng". Thứ chưa cần ở bước hiện tại thì chưa viết.

## Khi nào phải tách nhỏ

Tách một việc nếu nó:

- vừa đổi schema database vừa đổi logic tải/tách văn bản
- vừa đổi cách tìm kiếm vừa đổi cách viết câu trả lời
- dựa vào hành vi chưa có trong tài liệu

Nếu không kiểm chứng được trọn vẹn một cách nhanh chóng → việc quá rộng, tách tiếp.

## Khi thiếu hoặc mơ hồ yêu cầu

- Không đoán. Ghi câu hỏi vào mục "Câu hỏi còn mở" trong `progress-tracker.md` và hỏi người dùng.
- **Sự thật pháp lý không bao giờ được bịa:** số điều, mức phạt, ngưỡng, ngày hiệu lực, tên văn bản. Chưa đối chiếu với văn bản gốc thì ghi **chưa kiểm**.
- Tương tự với API, URL, giấy phép, giá dịch vụ: chưa kiểm thì ghi **chưa kiểm**, có nguồn thì dẫn nguồn.

## Việc không được tự làm — phải hỏi trước

- **Mọi lệnh git**, kể cả lệnh chỉ đọc (`status`, `diff`, `log`, `check-ignore`). Người dùng tự commit và push lên https://github.com/Shicukoe/TaxAssistant.
- **Hỏi mật khẩu, API key trong chat**, hoặc in giá trị bí mật ra màn hình. Người dùng tự điền `.env`; khi cần kiểm thì chỉ báo có/không, che giá trị.
- Xóa, di chuyển, dọn dẹp file — trong dự án hay ngoài dự án. Báo rủi ro, để người dùng tự làm.
- Thêm thư viện mới, thêm nguồn dữ liệu mới, tăng tốc độ tải.
- Biến một ĐỀ XUẤT thành quyết định.
- Thay đổi các quy tắc bất biến trong `architecture.md`.

## File được bảo vệ

Không sửa nếu không được yêu cầu rõ:

- `.env` — chỉ người dùng sửa (ngoại lệ: người dùng nhờ sửa một dòng cụ thể không phải bí mật).
- `data/raw/**` — bản gốc; chỉ bộ tải được thêm file, không ai sửa hay xóa.
- File migration đã chạy trong `app/db/migrations/` — muốn đổi thì thêm file mới.
- `app/db/create_app_user.sql` — chạy bằng tài khoản quản trị Postgres.

## Giữ tài liệu khớp với code

Code thay đổi điều nào thì sửa file tương ứng trong cùng lần làm:

| Thay đổi | Sửa file |
|---|---|
| Phạm vi, tính năng, luồng sử dụng | `project-overview.md` |
| Công nghệ, thư mục, lưu trữ, quy tắc bất biến, chi phí | `architecture.md` |
| Quy ước viết code | `code-standards.md` |
| Giao diện | `ui-context.md` |
| Phát hiện mới về nguồn dữ liệu, số liệu đo | `nguon-du-lieu.md` |
| Hiểu biết mới về thứ bậc, hiệu lực văn bản | `thu-bac-van-ban.md` |
| Thêm, đổi model, prompt, guardrail hoặc bài đo | `danh-gia.md` |
| Thêm, đổi công đoạn, bài kiểm hoặc lịch của pipeline | `pipeline-du-lieu.md` |
| Từ chuyên môn mới | `thuat-ngu.md` |
| Lệnh chạy, cấu trúc thư mục | `README.md` |
| Tiến độ, câu hỏi mở | `progress-tracker.md` |

## Trước khi sang việc tiếp theo

1. Việc hiện tại chạy trọn vẹn trong phạm vi của nó.
2. Mọi module đã sửa: `python -m app.<module> --check` in `PASS`.
3. Nếu đụng database: `python -m app.db.check_database` in `PASS`.
4. Không quy tắc bất biến nào trong `architecture.md` bị phá.
5. `progress-tracker.md` đã cập nhật.
6. Báo người dùng danh sách file đã đổi để họ tự commit.

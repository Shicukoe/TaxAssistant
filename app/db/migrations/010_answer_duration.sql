-- Tổng thời gian trả lời một câu, từ lúc nhận câu hỏi tới lúc lưu (trang Hiệu năng, docs/ui-context.md).
-- usage_log chỉ có thời gian của từng lần gọi model — thiếu tìm kiếm, kiểm trích dẫn, kiểm NLI (~16 giây trên CPU).
-- Câu trả lời lưu trước migration này để trống.
ALTER TABLE answers ADD COLUMN duration_ms integer;

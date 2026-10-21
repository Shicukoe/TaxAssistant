-- Hội thoại nhiều lượt và thời gian chạy model tự host.
-- thread_id  — nối câu hỏi với cuộc hội thoại trong checkpoint của LangGraph (bảng checkpoints).
--               questions/answers là bản ghi chính thức; checkpoint chỉ là trạng thái lúc chạy.
-- duration_ms — model chạy trên laptop không tốn tiền; thời gian mới là thứ cần đo (trang hiệu năng).
--               cost_usd giữ cho lời gọi giám khảo Claude, mặc định 0 cho model trên máy.
ALTER TABLE questions ADD COLUMN thread_id text;
CREATE INDEX questions_thread_idx ON questions (thread_id);

ALTER TABLE usage_log ADD COLUMN duration_ms integer;
ALTER TABLE usage_log ALTER COLUMN cost_usd SET DEFAULT 0;

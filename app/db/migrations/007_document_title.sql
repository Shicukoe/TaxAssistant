-- Tiêu đề (trích yếu) của văn bản — trang tra cứu cần hiện ("Thông tư hướng dẫn thuế môn bài").
-- Lấy từ trường "title" trong JSON cổng Bộ Tư pháp, ghi bởi app.ingest.save_to_database.
ALTER TABLE documents ADD COLUMN tieu_de text;

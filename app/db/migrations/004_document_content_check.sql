-- JSON của cổng Bộ Tư pháp đôi khi chứa văn bản khác (đo 22/10/2026: JSON của NĐ 125/2020 là
-- công văn đính chính 29/CP-KTTH). Trích từ đó sẽ ghi sai số hiệu → phá quy tắc bất biến số 1.
-- content_matches_number:
--   true  — số hiệu ghi ở đầu chữ văn bản khớp số hiệu của văn bản
--   false — khác: không bao giờ dùng văn bản này làm căn cứ
--   null  — đầu văn bản không ghi số, hoặc chưa có chữ: không kiểm được
-- Ghi bởi app.ingest.link_consolidated_documents.
ALTER TABLE documents ADD COLUMN content_matches_number boolean;

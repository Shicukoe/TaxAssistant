-- Mỗi văn bản ghi lại nó được nạp từ bản gốc nào và bằng bộ tách phiên bản nào.
-- raw_sha256     — sha256 của file JSON gốc trên đĩa lúc nạp
-- parser_version — app.ingest.split_articles.PARSER_VERSION lúc nạp
-- Hai cột này cho phép: chỉ nạp lại văn bản thật sự đổi (cổng Bộ Tư pháp có sửa văn bản sau khi
-- đăng), và truy được một Điều trong database sinh từ bản gốc nào.
ALTER TABLE documents
    ADD COLUMN raw_sha256     text,
    ADD COLUMN parser_version text;

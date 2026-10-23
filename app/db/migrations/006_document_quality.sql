-- Lớp 2 của "bốn lớp giữ dữ liệu sạch" (docs/architecture.md, Dữ liệu): mỗi văn bản một bộ kết quả kiểm
-- bất biến chung. Ghi bởi app.ingest.save_to_database (gọi app.ingest.check_document_quality), cùng
-- transaction với chữ của văn bản — nạp lại văn bản thì kết quả kiểm được tính lại.
CREATE TABLE document_checks (
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    check_name  text NOT NULL,          -- 'ma_chu' | 'thu_tu_de_muc' | 'do_phu' | 'doan_qua_dai'
    passed      boolean NOT NULL,
    severity    text NOT NULL CHECK (severity IN ('cach_ly', 'canh_bao')),
    detail      text,
    PRIMARY KEY (document_id, check_name)
);

-- Kết quả xem tay một văn bản bị cách ly. Gắn với bản gốc (source_uuid + raw_sha256), không gắn với
-- documents.id: nạp lại văn bản thì id đổi, còn kết quả xem tay vẫn giữ nếu bản gốc chưa đổi.
-- Bản gốc đổi (raw_sha256 khác) → kết quả cũ không còn áp dụng, phải xem lại.
CREATE TABLE document_reviews (
    source      text NOT NULL,
    source_uuid text NOT NULL,
    raw_sha256  text NOT NULL,
    verdict     text NOT NULL CHECK (verdict IN ('dung', 'sai')),  -- 'dung' = hết cách ly; 'sai' = giữ cách ly
    note        text,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_uuid, raw_sha256)
);

-- Văn bản đang bị cách ly: có phép kiểm nặng trượt và chưa được xem tay là "đúng" trên đúng bản gốc này.
-- Tìm kiếm, kiểm trích dẫn và trang tra cứu đều đọc view này — quy tắc cách ly nằm một chỗ.
CREATE VIEW quarantined_documents AS
SELECT d.id AS document_id, string_agg(c.check_name || ': ' || coalesce(c.detail, ''), ' | ') AS reasons
FROM documents d
JOIN document_checks c ON c.document_id = d.id AND NOT c.passed AND c.severity = 'cach_ly'
WHERE NOT EXISTS (
    SELECT 1 FROM document_reviews r
    WHERE r.source = d.source AND r.source_uuid = d.source_uuid AND r.raw_sha256 = d.raw_sha256
      AND r.verdict = 'dung')
GROUP BY d.id;

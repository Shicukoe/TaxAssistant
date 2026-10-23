-- Văn bản không có Điều (thông tư cũ) cắt theo đề mục (docs/architecture.md, Dữ liệu):
--   muc  — mục La Mã "II" hoặc mục số "3"; so = 'B.II' khi có phần chữ phía trên (mục II phần B)
--   doan — văn bản không có đề mục nào, cắt theo độ dài; so = '1', '2'...
-- Mục có tên ("II- CĂN CỨ TÍNH THUẾ") như Điều; khoản/điểm vẫn không có tên.
ALTER TABLE provisions DROP CONSTRAINT provisions_level_check;
ALTER TABLE provisions ADD CONSTRAINT provisions_level_check
    CHECK (level IN ('dieu', 'muc', 'doan', 'khoan', 'diem'));
ALTER TABLE provisions DROP CONSTRAINT provisions_ten_only_dieu;
ALTER TABLE provisions ADD CONSTRAINT provisions_ten_only_dieu
    CHECK (level IN ('dieu', 'muc') OR ten IS NULL);

ALTER TABLE chunk_positions DROP CONSTRAINT chunk_positions_level_check;
ALTER TABLE chunk_positions ADD CONSTRAINT chunk_positions_level_check
    CHECK (level IN ('dieu', 'muc', 'doan', 'khoan', 'diem'));

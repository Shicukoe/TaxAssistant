-- Tạo user riêng cho app + database của app. Chạy MỘT LẦN, bằng tài khoản quản trị postgres:
--
--     psql -U postgres -h 127.0.0.1 -f app/db/create_app_user.sql
--
-- psql sẽ hỏi: (1) mật khẩu của postgres, (2) mật khẩu MỚI cho taxassistant — gõ hai lần,
-- (3) có thể hỏi lại mật khẩu postgres khi chuyển sang database mới.
-- Mật khẩu mới của taxassistant chính là giá trị PGPASSWORD trong .env.
--
-- Vì sao tách user: app chỉ có quyền trên database của chính nó, không đụng được các
-- database khác trên máy, không tạo được user khác, không phải superuser.

\set ON_ERROR_STOP on

-- Tên viết thường toàn bộ → không cần ngoặc kép ở đâu cả.
CREATE ROLE taxassistant LOGIN;
\password taxassistant

-- App là chủ database của nó → tự tạo/sửa bảng được, nhưng chỉ trong database này.
CREATE DATABASE taxassistant OWNER taxassistant;
REVOKE ALL ON DATABASE taxassistant FROM PUBLIC;

\connect taxassistant
-- Extension cần quyền quản trị để cài → cài sẵn ở đây. Migration của app có
-- "CREATE EXTENSION IF NOT EXISTS" nên sẽ thấy đã có và bỏ qua.
-- Nếu dòng "vector" báo lỗi: pgvector chưa được cài cho PostgreSQL này — báo lại để xử lý.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\echo 'Xong: user taxassistant + database taxassistant + 3 extension.'

-- Tạo user riêng cho app + database của app, bằng tài khoản quản trị postgres:
--
--     psql -U postgres -h 127.0.0.1 -f app/db/create_app_user.sql
--
-- Chạy trong cmd hoặc Windows Terminal, không chạy trong Git Bash: psql trên Windows đọc mật khẩu
-- từ console, Git Bash không có console nên psql không hỏi được mật khẩu.
--
-- psql sẽ hỏi: (1) mật khẩu của postgres, (2) mật khẩu MỚI cho taxassistant — gõ hai lần,
-- (3) có thể hỏi lại mật khẩu postgres khi chuyển sang database mới.
-- Mật khẩu mới của taxassistant chính là giá trị PGPASSWORD trong .env.
--
-- Chạy lại được: user, database đã có thì bỏ qua (mật khẩu taxassistant vẫn được đặt lại).
--
-- Vì sao tách user: app chỉ có quyền trên database của chính nó, không đụng được các
-- database khác trên máy, không tạo được user khác, không phải superuser.

\set ON_ERROR_STOP on

-- Tên viết thường toàn bộ → không cần ngoặc kép ở đâu cả.
-- \gexec chạy câu lệnh do SELECT sinh ra; đã có thì SELECT không trả dòng nào → bỏ qua.
SELECT 'CREATE ROLE taxassistant LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taxassistant') \gexec
\password taxassistant

-- App là chủ database của nó → tự tạo/sửa bảng được, nhưng chỉ trong database này.
SELECT 'CREATE DATABASE taxassistant OWNER taxassistant'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'taxassistant') \gexec
REVOKE ALL ON DATABASE taxassistant FROM PUBLIC;

\connect taxassistant
-- Extension cần quyền quản trị để cài → cài sẵn ở đây. Migration của app có
-- "CREATE EXTENSION IF NOT EXISTS" nên sẽ thấy đã có và bỏ qua.
-- Nếu dòng "vector" báo lỗi: pgvector chưa được cài cho PostgreSQL này. Bản cài sẵn của
-- PostgreSQL trên Windows không kèm pgvector — xem docs/progress-tracker.md, phần ghi chú.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\echo 'Xong: user taxassistant + database taxassistant + 3 extension.'

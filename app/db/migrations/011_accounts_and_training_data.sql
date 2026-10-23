-- Tài khoản, phiên đăng nhập, mã OTP, hội thoại theo người, dữ liệu cho fine-tune / đánh giá.
-- Cách hoạt động và lý do từng phần: docs/architecture.md, mục Truy cập và phân quyền, mục Lưu trữ.
-- Mật khẩu, mã phiên, mã OTP không bao giờ lưu dạng gốc.

CREATE TABLE users (
    id             bigserial PRIMARY KEY,
    -- so khớp email không phân biệt hoa thường: luôn lưu chữ thường
    email          text NOT NULL UNIQUE CHECK (email = lower(email) AND email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    display_name   text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 80),
    -- chuỗi mã hoá Argon2id của argon2-cffi ($argon2id$v=19$m=…,t=…,p=…$salt$hash)
    password_hash  text NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    is_admin       boolean NOT NULL DEFAULT false,  -- thấy khung debug
    allow_training boolean NOT NULL DEFAULT false,  -- câu hỏi được dùng để fine-tune / đánh giá
    created_at     timestamptz NOT NULL DEFAULT now(),
    disabled_at    timestamptz
);

-- Chỉ lưu SHA-256 của mã phiên: lộ bảng này không dùng được để đăng nhập.
CREATE TABLE sessions (
    token_sha256 bytea PRIMARY KEY CHECK (length(token_sha256) = 32),
    user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token   text NOT NULL CHECK (length(csrf_token) >= 32),
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL  -- hết hạn tuyệt đối; hết hạn vì không dùng tính từ last_seen_at
);
CREATE INDEX sessions_user_idx ON sessions (user_id);

-- Mã OTP gửi qua email: chỉ lưu HMAC-SHA256 (khoá AUTH_SECRET trong .env, không nằm trong database).
CREATE TABLE email_codes (
    id              bigserial PRIMARY KEY,
    email           text NOT NULL CHECK (email = lower(email)),
    purpose         text NOT NULL CHECK (purpose IN ('dang_ky', 'dat_lai_mat_khau')),
    code_hmac       bytea CHECK (code_hmac IS NULL OR length(code_hmac) = 32),  -- trống: email nhắc, không có mã
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    failed_attempts smallint NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    used_at         timestamptz
);
CREATE INDEX email_codes_email_idx ON email_codes (email, created_at);
CREATE INDEX email_codes_created_idx ON email_codes (created_at);

CREATE TABLE login_attempts (
    id           bigserial PRIMARY KEY,
    email        text NOT NULL CHECK (email = lower(email)),
    attempted_at timestamptz NOT NULL DEFAULT now(),
    succeeded    boolean NOT NULL
);
CREATE INDEX login_attempts_email_idx ON login_attempts (email, attempted_at);

-- Chủ của từng cuộc hội thoại. user_id trống: hội thoại từ terminal hoặc từ trước khi có tài khoản —
-- không hiện trên web cho tới khi gán chủ bằng app/web/manage_users.py.
CREATE TABLE conversations (
    thread_id  text PRIMARY KEY,
    user_id    bigint REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    hidden_at  timestamptz  -- nút xoá trên web chỉ ẩn; dữ liệu giữ cho fine-tune / đánh giá
);
CREATE INDEX conversations_user_idx ON conversations (user_id);

INSERT INTO conversations (thread_id, created_at)
SELECT thread_id, min(asked_at) FROM questions WHERE thread_id IS NOT NULL GROUP BY thread_id;
ALTER TABLE questions ADD CONSTRAINT questions_thread_fk
    FOREIGN KEY (thread_id) REFERENCES conversations(thread_id);

-- Đúng thứ model đã nhận và trả cho mỗi lời gọi — nguyên liệu fine-tune. request là body gửi llama-server
-- (messages, thông số lấy mẫu, JSON schema); prompt nằm trong request nên không cần số phiên bản prompt riêng.
CREATE TABLE model_calls (
    id          bigserial PRIMARY KEY,
    question_id bigint NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    step        text NOT NULL,
    model       text NOT NULL,
    request     jsonb NOT NULL CHECK (jsonb_typeof(request -> 'messages') = 'array'),
    output      text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_calls_question_idx ON model_calls (question_id);

-- Người hỏi chấm câu trả lời — ba nhãn của Magesh (docs/danh-gia.md). Chấm lại thì ghi đè.
CREATE TABLE answer_feedback (
    answer_id  bigint PRIMARY KEY REFERENCES answers(id) ON DELETE CASCADE,
    user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    verdict    text NOT NULL CHECK (verdict IN ('dung', 'sai', 'chua_du')),
    note       text CHECK (length(note) <= 2000),
    updated_at timestamptz NOT NULL DEFAULT now()
);

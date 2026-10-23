"""Tài khoản, mật khẩu, phiên đăng nhập, mã CSRF (docs/architecture.md, Truy cập và phân quyền — theo OWASP
Password Storage, Session Management cheat sheet).

Mật khẩu băm Argon2id bằng argon2-cffi với thông số mặc định của thư viện (profile RFC 9106 low-memory). Phiên là
mã ngẫu nhiên 256 bit; database chỉ giữ SHA-256 của mã. Hàm nhận `conn` để gói nhiều bước trong một transaction
(send_email_codes: kiểm mã OTP rồi tạo tài khoản).

Chạy bài tự kiểm: python -m app.web.authenticate_users --check
"""

import asyncio
import hashlib
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app import config

SESSION_COOKIE = "__Host-phien"  # __Host-: bắt buộc Secure, Path=/, không Domain — cookie chỉ về đúng app
SESSION_IDLE = timedelta(days=7)
SESSION_LIFETIME = timedelta(days=30)
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)  # ghi last_seen_at thưa hơn mỗi request
MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_CHARS = 128  # chặn mật khẩu cực dài làm tốn CPU khi băm
MAX_FAILED_LOGINS = 5
LOGIN_LOCK_WINDOW = timedelta(minutes=15)
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")  # cùng mẫu với CHECK của users.email (migration 011)

password_hasher = PasswordHasher()


@dataclass(frozen=True)
class User:
    id: int
    email: str
    display_name: str
    is_admin: bool


@dataclass(frozen=True)
class Session:
    user: User
    csrf_token: str


def normalize_email(text: str) -> str:
    """Email chữ thường, bỏ khoảng trắng; không đúng dạng → chuỗi rỗng."""
    email = text.strip().lower()
    return email if len(email) <= 254 and EMAIL_PATTERN.fullmatch(email) else ""


def password_problem(password: str, email: str) -> str | None:
    """Lý do mật khẩu không dùng được, hoặc None. Không ép ký tự đặc biệt — cụm từ dài dễ nhớ hơn và khó đoán hơn."""
    if len(password) < MIN_PASSWORD_CHARS:
        return f"Mật khẩu cần ít nhất {MIN_PASSWORD_CHARS} ký tự."
    if len(password) > MAX_PASSWORD_CHARS:
        return f"Mật khẩu tối đa {MAX_PASSWORD_CHARS} ký tự."
    if password.strip().lower() == email:
        return "Mật khẩu không được trùng email."
    return None


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """Bản băm giả: email không có tài khoản vẫn chạy một lần verify → thời gian trả lời như email có tài khoản."""
    return password_hasher.hash(secrets.token_hex(16))


async def hash_password(password: str) -> str:
    # Argon2 tốn ~64 MiB và vài chục ms CPU — chạy ngoài event loop
    return await asyncio.to_thread(password_hasher.hash, password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, ValueError):  # ValueError gồm InvalidHashError và bản băm có ký tự ngoài ASCII
        return False


async def check_login(email: str, password: str) -> tuple[User | None, str | None]:
    """(người dùng, None) nếu đúng; (None, thông báo) nếu sai. Thông báo không cho biết email có tài khoản hay không."""
    wrong = "Email hoặc mật khẩu không đúng."
    email = normalize_email(email)
    if not email:
        return None, wrong
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        [failed] = await (await conn.execute(
            "select count(*) from login_attempts where email = %s and not succeeded and attempted_at > now() - %s",
            (email, LOGIN_LOCK_WINDOW))).fetchone()
        if failed >= MAX_FAILED_LOGINS:
            return None, "Nhập sai nhiều lần — thử lại sau 15 phút."
        row = await (await conn.execute(
            "select id, email, display_name, is_admin, password_hash from users "
            "where email = %s and disabled_at is null", (email,))).fetchone()
        matched = await asyncio.to_thread(verify_password, row[4] if row else dummy_hash(), password)
        matched = matched and row is not None
        await conn.execute("insert into login_attempts (email, succeeded) values (%s, %s)", (email, matched))
        if not matched:
            return None, wrong
        if password_hasher.check_needs_rehash(row[4]):  # thông số thư viện đổi → băm lại lúc còn mật khẩu gốc
            await conn.execute("update users set password_hash = %s where id = %s", (await hash_password(password), row[0]))
        return User(*row[:4]), None


async def create_session(user_id: int) -> str:
    """Phiên mới (mỗi lần đăng nhập một mã mới — chống session fixation). Trả mã để đặt vào cookie."""
    token = secrets.token_urlsafe(32)
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        await conn.execute(
            "insert into sessions (token_sha256, user_id, csrf_token, expires_at) values (%s, %s, %s, now() + %s)",
            (token_digest(token), user_id, secrets.token_urlsafe(32), SESSION_LIFETIME))
    return token


async def find_session(token: str) -> Session | None:
    """Phiên còn hạn (chưa quá hạn tuyệt đối, chưa quá SESSION_IDLE không dùng) của tài khoản chưa bị khoá."""
    if not token:
        return None
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        row = await (await conn.execute(
            """update sessions s set last_seen_at = case when s.last_seen_at < now() - %(touch)s then now()
                                                         else s.last_seen_at end
               from users u
               where s.token_sha256 = %(digest)s and u.id = s.user_id and u.disabled_at is null
                 and s.expires_at > now() and s.last_seen_at > now() - %(idle)s
               returning u.id, u.email, u.display_name, u.is_admin, s.csrf_token""",
            {"digest": token_digest(token), "touch": SESSION_TOUCH_INTERVAL, "idle": SESSION_IDLE})).fetchone()
    return Session(User(*row[:4]), row[4]) if row else None


async def end_session(token: str) -> None:
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        await conn.execute("delete from sessions where token_sha256 = %s", (token_digest(token),))


async def email_has_account(conn: psycopg.AsyncConnection, email: str) -> bool:
    return await (await conn.execute("select 1 from users where email = %s", (email,))).fetchone() is not None


async def create_user(conn: psycopg.AsyncConnection, email: str, display_name: str, password: str) -> bool:
    """False nếu email đã có tài khoản."""
    cursor = await conn.execute(
        "insert into users (email, display_name, password_hash) values (%s, %s, %s) "
        "on conflict (email) do nothing returning id", (email, display_name, await hash_password(password)))
    return await cursor.fetchone() is not None


async def set_password(conn: psycopg.AsyncConnection, email: str, password: str) -> bool:
    """Đặt mật khẩu mới và huỷ mọi phiên của tài khoản (OWASP Forgot Password). False nếu không có tài khoản."""
    row = await (await conn.execute("update users set password_hash = %s where email = %s returning id",
                                    (await hash_password(password), email))).fetchone()
    if row is None:
        return False
    await conn.execute("delete from sessions where user_id = %s", (row[0],))
    return True


def self_check() -> None:
    assert normalize_email("  Me@Example.COM ") == "me@example.com"
    assert normalize_email("khong-phai-email") == "" and normalize_email("a@b") == ""
    assert password_problem("ngắn", "a@b.vn") is not None
    assert password_problem("a@b.vn" + " " * 6, "a@b.vn") is not None
    assert password_problem("mẹ hỏi thuế mỗi ngày", "a@b.vn") is None
    assert password_problem("x" * (MAX_PASSWORD_CHARS + 1), "a@b.vn") is not None
    stored = password_hasher.hash("mẹ hỏi thuế mỗi ngày")
    assert stored.startswith("$argon2id$")  # khớp CHECK của users.password_hash
    assert verify_password(stored, "mẹ hỏi thuế mỗi ngày") and not verify_password(stored, "sai")
    assert not verify_password("không phải bản băm", "x")
    assert len(token_digest("abc")) == 32  # khớp CHECK của sessions.token_sha256
    print("PASS")


if __name__ == "__main__":
    if "--check" in sys.argv:
        self_check()

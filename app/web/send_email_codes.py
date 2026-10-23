"""Mã OTP qua email cho đăng ký và đặt lại mật khẩu (docs/architecture.md, Truy cập và phân quyền — theo OWASP
Forgot Password cheat sheet).

Mã 6 chữ số từ `secrets`, dùng một lần, hết hạn sau 10 phút, sai 5 lần thì huỷ. Database chỉ giữ HMAC-SHA256 của
mã (khoá AUTH_SECRET trong .env) gắn với email và mục đích — lộ database không đoán được mã, mã đăng ký không dùng
được để đặt lại mật khẩu. Mọi trường hợp (email đã có / chưa có / vượt giới hạn) đều trả cùng một câu; email gửi ở
nền nên thời gian trả lời như nhau. Gửi bằng smtplib (thư viện chuẩn) qua SMTP có TLS.

Chạy bài tự kiểm: python -m app.web.send_email_codes --check
"""

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import ssl
import sys
from datetime import timedelta
from email.message import EmailMessage

import psycopg

from app import config
from app.web.authenticate_users import create_user, email_has_account, normalize_email, password_problem, set_password

log = logging.getLogger(__name__)

REGISTER = "dang_ky"
RESET_PASSWORD = "dat_lai_mat_khau"
CODE_DIGITS = 6
CODE_LIFETIME = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5
RESEND_GAP = timedelta(seconds=60)
MAX_CODES_PER_EMAIL_PER_HOUR = 5  # không ai dùng app để dội thư vào hộp thư người khác
MAX_EMAILS_PER_HOUR = 30  # cả app — giữ tài khoản Gmail gửi mã không bị khoá vì gửi hàng loạt
WRONG_CODE = "Mã không đúng hoặc đã hết hạn. Yêu cầu mã mới nếu cần."
PURPOSE_TEXT = {REGISTER: "tạo tài khoản", RESET_PASSWORD: "đặt lại mật khẩu"}
MAX_DISPLAY_NAME_CHARS = 80

sending_tasks: set[asyncio.Task] = set()  # giữ tham chiếu để task gửi nền không bị thu dọn giữa chừng


def new_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def code_hmac(email: str, purpose: str, code: str) -> bytes:
    key = config.require_env("AUTH_SECRET").encode()
    return hmac.new(key, f"{purpose}\n{email}\n{code}".encode(), hashlib.sha256).digest()


def code_email(email: str, purpose: str, code: str | None) -> EmailMessage:
    """Email chứa mã; code None → email nhắc tài khoản đã có (đăng ký bằng email đã đăng ký)."""
    message = EmailMessage()
    message["From"] = config.SMTP_USER
    message["To"] = email
    if code is None:
        message["Subject"] = "Tax Assistant: email này đã có tài khoản"
        message.set_content(
            "Có người vừa đăng ký Tax Assistant bằng email này, nhưng email này đã có tài khoản.\n"
            "Nếu quên mật khẩu, bấm \"Quên mật khẩu\" ở trang đăng nhập.\n"
            "Nếu không phải bạn, bỏ qua email này — không ai vào được tài khoản nếu không có mật khẩu.")
        return message
    message["Subject"] = f"Tax Assistant: mã xác nhận để {PURPOSE_TEXT[purpose]}"
    message.set_content(
        f"Mã xác nhận để {PURPOSE_TEXT[purpose]}: {code}\n\n"
        f"Mã dùng một lần, hết hạn sau {CODE_LIFETIME.seconds // 60} phút. Không gửi mã này cho ai.\n"
        "Nếu bạn không yêu cầu, bỏ qua email này.")
    return message


def send_email(message: EmailMessage) -> None:
    try:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ssl.create_default_context(),
                              timeout=20) as server:
            server.login(config.SMTP_USER, config.require_env("SMTP_PASSWORD"))
            server.send_message(message)
    except (OSError, smtplib.SMTPException, RuntimeError) as error:
        # Không ghi nội dung thư (có mã) hay địa chỉ người nhận ra log
        log.error("Gửi email mã xác nhận thất bại: %s", type(error).__name__)


async def request_code(email_text: str, purpose: str) -> None:
    """Ghi mã mới (nếu được phép) rồi gửi email ở nền. Không trả gì: người gọi luôn hiện cùng một câu."""
    email = normalize_email(email_text)
    if not email:
        return
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        async with conn.transaction():
            # Hai yêu cầu cùng lúc không cùng lọt qua giới hạn
            await conn.execute("select pg_advisory_xact_lock(hashtext('email_codes'))")
            per_email, last_sent, total = await (await conn.execute(
                """select count(*) filter (where email = %(email)s), max(created_at) filter (where email = %(email)s)
                          > now() - %(gap)s, count(*)
                   from email_codes where created_at > now() - interval '1 hour'""",
                {"email": email, "gap": RESEND_GAP})).fetchone()
            if per_email >= MAX_CODES_PER_EMAIL_PER_HOUR or last_sent or total >= MAX_EMAILS_PER_HOUR:
                return
            has_account = await email_has_account(conn, email)
            if purpose == RESET_PASSWORD and not has_account:
                return
            code = None if purpose == REGISTER and has_account else new_code()
            await conn.execute(
                "insert into email_codes (email, purpose, code_hmac, expires_at) values (%s, %s, %s, now() + %s)",
                (email, purpose, code_hmac(email, purpose, code) if code else None, CODE_LIFETIME))
    task = asyncio.create_task(asyncio.to_thread(send_email, code_email(email, purpose, code)))
    sending_tasks.add(task)
    task.add_done_callback(sending_tasks.discard)


async def use_code(conn: psycopg.AsyncConnection, email: str, purpose: str, code: str) -> bool:
    """Kiểm mã mới nhất còn hạn của email + mục đích. Đúng → đánh dấu đã dùng (cả các mã cũ hơn); sai → tăng đếm."""
    row = await (await conn.execute(
        """select id, code_hmac, failed_attempts from email_codes
           where email = %s and purpose = %s and code_hmac is not null and used_at is null and expires_at > now()
           order by created_at desc limit 1 for update""", (email, purpose))).fetchone()
    if row is None or row[2] >= MAX_CODE_ATTEMPTS:
        return False
    if not hmac.compare_digest(row[1], code_hmac(email, purpose, code.strip())):
        await conn.execute("update email_codes set failed_attempts = failed_attempts + 1 where id = %s", (row[0],))
        return False
    await conn.execute("update email_codes set used_at = now() where email = %s and purpose = %s and used_at is null",
                       (email, purpose))
    return True


async def complete_registration(email_text: str, code: str, display_name: str, password: str) -> str | None:
    """Tạo tài khoản khi mã đúng. Trả thông báo lỗi, hoặc None nếu xong."""
    email, display_name = normalize_email(email_text), " ".join(display_name.split())
    if not email:
        return WRONG_CODE
    if not 1 <= len(display_name) <= MAX_DISPLAY_NAME_CHARS:
        return f"Tên hiển thị cần 1–{MAX_DISPLAY_NAME_CHARS} ký tự."
    if problem := password_problem(password, email):
        return problem
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        if not await use_code(conn, email, REGISTER, code):
            return WRONG_CODE
        if not await create_user(conn, email, display_name, password):
            return WRONG_CODE
    return None


async def complete_password_reset(email_text: str, code: str, password: str) -> str | None:
    """Đặt mật khẩu mới khi mã đúng; mọi phiên cũ bị huỷ. Trả thông báo lỗi, hoặc None nếu xong."""
    email = normalize_email(email_text)
    if not email:
        return WRONG_CODE
    if problem := password_problem(password, email):
        return problem
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        if not await use_code(conn, email, RESET_PASSWORD, code) or not await set_password(conn, email, password):
            return WRONG_CODE
    return None


def self_check() -> None:
    os.environ.setdefault("AUTH_SECRET", "khoa-chi-de-tu-kiem")  # .env chưa có khoá thì vẫn tự kiểm được
    codes = {new_code() for _ in range(200)}
    assert all(len(c) == CODE_DIGITS and c.isdigit() for c in codes) and len(codes) > 150
    digest = code_hmac("a@b.vn", REGISTER, "012345")
    assert len(digest) == 32  # khớp CHECK của email_codes.code_hmac
    assert digest != code_hmac("a@b.vn", RESET_PASSWORD, "012345"), "mã đăng ký không dùng được để đặt lại mật khẩu"
    assert digest != code_hmac("c@b.vn", REGISTER, "012345")
    with_code = code_email("a@b.vn", REGISTER, "012345").get_content()
    assert "012345" in with_code and "10 phút" in with_code
    assert "012345" not in code_email("a@b.vn", REGISTER, None).get_content()
    print("PASS")


if __name__ == "__main__":
    if "--check" in sys.argv:
        self_check()

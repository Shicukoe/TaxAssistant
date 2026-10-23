"""Quản lý tài khoản trên laptop — không có trang web cho việc này (docs/architecture.md, Truy cập và phân quyền).

    python -m app.web.manage_users                                  danh sách tài khoản, số hội thoại chưa có chủ
    python -m app.web.manage_users --quan-tri <email> bat|tat       quyền quản trị (thấy khung debug)
    python -m app.web.manage_users --huan-luyen <email> bat|tat     cho phép dùng câu hỏi để fine-tune / đánh giá
    python -m app.web.manage_users --khoa <email> bat|tat           khoá tài khoản (huỷ mọi phiên) / mở khoá
    python -m app.web.manage_users --nhan-hoi-thoai-cu <email>      gán mọi hội thoại chưa có chủ cho tài khoản này
    python -m app.web.manage_users --xoa-hoi-thoai <thread_id>      xoá hẳn một cuộc hội thoại (câu hỏi, câu trả lời,
                                                                    đánh giá, lời gọi model, checkpoint)
"""

import sys

import psycopg
from psycopg import sql

from app import config

FLAG_COLUMNS = {"--quan-tri": "is_admin", "--huan-luyen": "allow_training"}
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")  # bảng do LangGraph .setup() tạo


def list_users(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        """select u.email, u.display_name, u.is_admin, u.allow_training, u.disabled_at is not null,
                  count(c.thread_id) filter (where c.hidden_at is null), count(c.thread_id) filter (where c.hidden_at is not null)
           from users u left join conversations c on c.user_id = u.id
           group by u.id order by u.created_at""").fetchall()
    for email, name, admin, training, disabled, visible, hidden in rows:
        flags = ", ".join(f for f, on in (("quản trị", admin), ("huấn luyện", training), ("KHOÁ", disabled)) if on)
        print(f"{email:<36} {name:<24} {visible} hội thoại (+{hidden} đã ẩn)  {flags}")
    [orphans] = conn.execute("select count(*) from conversations where user_id is null").fetchone()
    print(f"{len(rows)} tài khoản · {orphans} hội thoại chưa có chủ (terminal hoặc từ trước khi có tài khoản)")


def user_id_of(conn: psycopg.Connection, email: str) -> int:
    row = conn.execute("select id from users where email = %s", (email.strip().lower(),)).fetchone()
    if row is None:
        raise SystemExit(f"Không có tài khoản {email}")
    return row[0]


def switch_value(text: str) -> bool:
    if text not in ("bat", "tat"):
        raise SystemExit("Giá trị phải là 'bat' hoặc 'tat'")
    return text == "bat"


def main() -> None:
    args = sys.argv[1:]
    with psycopg.connect(config.DATABASE_CONNECTION) as conn:
        if not args:
            list_users(conn)
        elif args[0] in FLAG_COLUMNS and len(args) == 3:
            user_id = user_id_of(conn, args[1])
            conn.execute(sql.SQL("update users set {} = %s where id = %s").format(sql.Identifier(FLAG_COLUMNS[args[0]])),
                         (switch_value(args[2]), user_id))
            print("Đã đổi.")
        elif args[0] == "--khoa" and len(args) == 3:
            user_id = user_id_of(conn, args[1])
            locked = switch_value(args[2])
            conn.execute("update users set disabled_at = case when %s then now() end where id = %s", (locked, user_id))
            if locked:
                conn.execute("delete from sessions where user_id = %s", (user_id,))
            print("Đã khoá, mọi phiên bị huỷ." if locked else "Đã mở khoá.")
        elif args[0] == "--nhan-hoi-thoai-cu" and len(args) == 2:
            user_id = user_id_of(conn, args[1])
            count = conn.execute("update conversations set user_id = %s where user_id is null", (user_id,)).rowcount
            print(f"Đã gán {count} hội thoại.")
        elif args[0] == "--xoa-hoi-thoai" and len(args) == 2:
            thread_id = args[1]
            with conn.transaction():
                # answers, model_calls, answer_feedback xoá theo khoá ngoại ON DELETE CASCADE từ questions
                questions = conn.execute("delete from questions where thread_id = %s", (thread_id,)).rowcount
                for table in CHECKPOINT_TABLES:
                    conn.execute(sql.SQL("delete from {} where thread_id = %s").format(sql.Identifier(table)),
                                 (thread_id,))
                conn.execute("delete from conversations where thread_id = %s", (thread_id,))
            print(f"Đã xoá hẳn {questions} câu hỏi của cuộc hội thoại {thread_id}.")
        else:
            print(__doc__)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

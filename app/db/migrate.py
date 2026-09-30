"""Migration runner: chạy các file .sql theo thứ tự tên, mỗi file đúng một lần.

ponytail: không dùng Alembic. Migration của project này là forward-only và do một
người viết — một bảng schema_migrations cộng vòng lặp này là đủ. Dùng Alembic khi
nào cần autogenerate từ ORM hoặc cần downgrade thật.
"""

import sys
from pathlib import Path

import psycopg
from psycopg import sql

from app import config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def ensure_database() -> bool:
    """Tạo PGDATABASE nếu chưa có. Trả về True nếu vừa tạo mới."""
    with psycopg.connect(config.ADMIN_DSN, autocommit=True) as conn:
        exists = conn.execute(
            "select 1 from pg_database where datname = %s", (config.PGDATABASE,)
        ).fetchone()
        if exists:
            return False
        # Tên DB không tham số hoá được trong CREATE DATABASE → quote bằng identifier.
        conn.execute(
            sql.SQL("create database {}").format(sql.Identifier(config.PGDATABASE))
        )
        return True


def applied_migrations(conn: psycopg.Connection) -> set[str]:
    conn.execute(
        """
        create table if not exists schema_migrations (
            filename   text primary key,
            applied_at timestamptz not null default now()
        )
        """
    )
    return {r[0] for r in conn.execute("select filename from schema_migrations")}


def migrate() -> list[str]:
    """Chạy các migration chưa áp dụng. Trả về danh sách file vừa chạy."""
    created = ensure_database()
    if created:
        print(f"đã tạo database {config.PGDATABASE}")

    ran: list[str] = []
    with psycopg.connect(config.DSN) as conn:
        done = applied_migrations(conn)
        conn.commit()

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            print(f"áp dụng {path.name} ...", end=" ", flush=True)
            # Mỗi migration trong một transaction: lỗi giữa đường không để lại schema nửa vời.
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "insert into schema_migrations (filename) values (%s)", (path.name,)
                )
            print("xong")
            ran.append(path.name)

    if not ran:
        print("không có migration mới")
    return ran


if __name__ == "__main__":
    try:
        migrate()
    except psycopg.errors.FeatureNotSupported as e:
        # Nhánh đã lường trước: pgvector thường thiếu trên PG Windows.
        print(f"\nLỖI: {e}", file=sys.stderr)
        print(
            "Nếu lỗi nói về extension 'vector': pgvector chưa được cài cho PostgreSQL này.\n"
            "Hai đường: cài pgvector cho PG18 native, hoặc chạy Postgres trong Docker\n"
            "với image đã có pgvector sẵn rồi trỏ .env sang cổng đó.",
            file=sys.stderr,
        )
        sys.exit(1)
    except psycopg.Error as e:
        print(f"\nLỖI: {e}", file=sys.stderr)
        sys.exit(1)

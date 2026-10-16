"""Dựng database: tạo database nếu chưa có, rồi chạy các file .sql trong migrations/
theo thứ tự tên, mỗi file đúng một lần.

Chạy:  python -m app.db.setup_database
"""

import sys
from pathlib import Path

import psycopg
from psycopg import sql

from app import config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def create_database_if_missing() -> bool:
    """Tạo database của app nếu chưa có. Trả về True nếu vừa tạo mới."""
    config.require_env("PGPASSWORD")
    with psycopg.connect(config.ADMIN_DATABASE_CONNECTION, autocommit=True) as conn:
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


def list_applied_migrations(conn: psycopg.Connection) -> set[str]:
    """Tên các file migration đã chạy (bảng schema_migrations tự tạo nếu chưa có)."""
    conn.execute(
        """
        create table if not exists schema_migrations (
            filename   text primary key,
            applied_at timestamptz not null default now()
        )
        """
    )
    return {r[0] for r in conn.execute("select filename from schema_migrations")}


def apply_migrations() -> list[str]:
    """Chạy các migration chưa áp dụng. Trả về danh sách file vừa chạy."""
    if create_database_if_missing():
        print(f"đã tạo database {config.PGDATABASE}")

    applied_now: list[str] = []
    with psycopg.connect(config.DATABASE_CONNECTION) as conn:
        already_applied = list_applied_migrations(conn)
        conn.commit()

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already_applied:
                continue
            print(f"áp dụng {path.name} ...", end=" ", flush=True)
            # Mỗi migration trong một transaction: lỗi giữa đường không để lại schema nửa vời.
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "insert into schema_migrations (filename) values (%s)", (path.name,)
                )
            print("xong")
            applied_now.append(path.name)

    if not applied_now:
        print("không có migration mới")
    return applied_now


if __name__ == "__main__":
    try:
        apply_migrations()
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

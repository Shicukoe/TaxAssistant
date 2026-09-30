"""Bài tự kiểm cho database. Chạy: python -m app.selfcheck

ponytail: một check chạy được, không framework. Nó fail nếu schema sai, nếu
migration không idempotent, hoặc nếu full-text tiếng Việt không bỏ dấu được —
ba thứ mà mọi thứ về sau dựa lên.
"""

import psycopg

from app import config
from app.db.migrate import migrate

TABLES = [
    "documents",
    "document_relations",
    "provisions",
    "chunks",
    "chunk_positions",
    "amendments",
    "embeddings",
    "questions",
    "answers",
    "usage_log",
]


def check_migrations_idempotent() -> None:
    migrate()
    assert migrate() == [], "migrate() chạy lần hai phải không làm gì — hiện có làm"
    print("ok  migration idempotent")


def check_schema(conn: psycopg.Connection) -> None:
    found = {
        r[0]
        for r in conn.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        )
    }
    missing = [t for t in TABLES if t not in found]
    assert not missing, f"thiếu bảng: {missing}"

    exts = {r[0] for r in conn.execute("select extname from pg_extension")}
    for e in ("vector", "unaccent", "pg_trgm"):
        assert e in exts, f"thiếu extension {e}"
    print(f"ok  {len(TABLES)} bảng + 3 extension")


def check_roundtrip(conn: psycopg.Connection) -> None:
    """Ghi rồi đọc lại xuyên documents → provisions → chunks → chunk_positions.

    Rollback ở cuối nên DB không bị bẩn.
    """
    try:
        with conn.transaction():
            doc_id = conn.execute(
                """
                insert into documents (source, source_uuid, source_url, so_hieu, loai,
                                       doc_group, text_origin, eff_from)
                values ('moj_gateway', 'selfcheck', 'https://example.invalid',
                        '00/2026/TT-BTC', 'Thông tư', 'VBQPPL', 'native', '2026-01-01')
                returning id
                """
            ).fetchone()[0]

            dieu_id = conn.execute(
                """
                insert into provisions (document_id, level, so, ten, ordinal, text, parsed_by)
                values (%s, 'dieu', '13', 'Xử phạt hành vi vi phạm về thời hạn nộp hồ sơ khai thuế',
                        1, 'Điều 13. ... Phạt tiền đối với hành vi lập hóa đơn không đúng quy định',
                        'markup')
                returning id
                """,
                (doc_id,),
            ).fetchone()[0]

            khoan_id = conn.execute(
                """
                insert into provisions (document_id, level, so, parent_id, ordinal, text, parsed_by)
                values (%s, 'khoan', '4', %s, 2, 'Phạt tiền từ 8.000.000 đồng đến 15.000.000 đồng',
                        'regex')
                returning id
                """,
                (doc_id, dieu_id),
            ).fetchone()[0]

            chunk_text = (
                "Điều 13. Xử phạt hành vi vi phạm về thời hạn nộp hồ sơ khai thuế\n"
                "4. Phạt tiền từ 8.000.000 đồng đến 15.000.000 đồng đối với hành vi "
                "lập hóa đơn không đúng quy định"
            )
            chunk_id = conn.execute(
                """
                insert into chunks (document_id, dieu_provision_id, text, token_count)
                values (%s, %s, %s, 42) returning id
                """,
                (doc_id, dieu_id, chunk_text),
            ).fetchone()[0]

            conn.execute(
                """
                insert into chunk_positions (chunk_id, provision_id, level, so,
                                             char_start, char_end)
                values (%s, %s, 'khoan', '4', 66, %s)
                """,
                (chunk_id, khoan_id, len(chunk_text)),
            )

            # Đối chiếu vị trí: đây là cơ chế chống trích dẫn bịa.
            span = conn.execute(
                """
                select substring(c.text from p.char_start + 1 for p.char_end - p.char_start)
                from chunk_positions p join chunks c on c.id = p.chunk_id
                where p.chunk_id = %s
                """,
                (chunk_id,),
            ).fetchone()[0]
            assert "8.000.000" in span, f"span đọc ra không đúng: {span!r}"

            # Full-text bỏ dấu: truy vấn KHÔNG dấu phải tìm được văn bản CÓ dấu.
            # Nếu assert này fail thì toàn bộ hướng full-text tiếng Việt sai từ gốc.
            hit = conn.execute(
                """
                select 1 from chunks
                where id = %s
                  and fts @@ to_tsquery('simple', f_unaccent('hoa') || ' & ' || f_unaccent('don'))
                """,
                (chunk_id,),
            ).fetchone()
            assert hit, "full-text không match 'hoa don' với text 'hóa đơn' — unaccent sai"

            # embeddings: cột vector để không chiều (chưa chọn model)
            conn.execute(
                """
                insert into embeddings (chunk_id, model_name, model_version, dim, vec)
                values (%s, 'selfcheck', 'v0', 3, '[0.1,0.2,0.3]')
                """,
                (chunk_id,),
            )

            raise psycopg.Rollback
    except psycopg.Rollback:
        pass

    left = conn.execute(
        "select count(*) from documents where source_uuid = 'selfcheck'"
    ).fetchone()[0]
    assert left == 0, "rollback không sạch — DB còn dữ liệu của self-check"
    print("ok  round-trip documents→provisions→chunks→chunk_positions, đối chiếu span, unaccent")


def check_constraints(conn: psycopg.Connection) -> None:
    """Các CHECK phải thật sự cắn. Constraint không cắn là constraint không tồn tại."""
    cases = [
        (
            "khoản không được có tên (Luật 64/2025 Điều 7 khoản 2)",
            """insert into provisions (document_id, level, so, ten, ordinal, text, parsed_by)
               select id, 'khoan', '1', 'tên sai', 1, 'x', 'markup' from documents limit 1""",
        ),
        (
            "text_origin chỉ nhận native|ocr|none (chữ OCR phải được đánh dấu)",
            """insert into documents (source, source_url, doc_group, text_origin)
               values ('x', 'y', 'VBQPPL', 'guessed')""",
        ),
        (
            "amendments kiểu cum_tu phải có phrase_from/phrase_to",
            """insert into amendments (target_document_id, target_kind, amending_ref_text,
                                       footnote_text)
               select id, 'cum_tu', 'ref', 'fn' from documents limit 1""",
        ),
    ]
    for label, sql in cases:
        try:
            with conn.transaction():
                conn.execute(sql)
                raise AssertionError(f"constraint KHÔNG cắn: {label}")
        except (psycopg.errors.CheckViolation, psycopg.errors.NotNullViolation):
            pass
    print(f"ok  {len(cases)} constraint đều cắn")


def main() -> None:
    check_migrations_idempotent()
    with psycopg.connect(config.DSN) as conn:
        check_schema(conn)
        check_roundtrip(conn)
        check_constraints(conn)
    print("\nPASS")


if __name__ == "__main__":
    main()

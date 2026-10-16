"""Nạp văn bản thuế từ bản gốc trên đĩa vào database: documents → provisions → chunks → chunk_positions.

Chạy (sau download_moj_documents, cần .env; trong pipeline: công đoạn save_documents_to_database):
    python -m app.ingest.save_to_database

Chỉ nạp văn bản mới hoặc đã đổi: mỗi dòng documents ghi raw_sha256 (bản gốc) và parser_version
(bộ tách) — giống cả hai thì bỏ qua. Văn bản đổi thì xoá rồi nạp lại trong một transaction.
Một văn bản lỗi chỉ được ghi vào báo cáo, các văn bản khác vẫn nạp.
Văn bản chưa tách được (không có Điều, chỉ có file đính kèm) vẫn có dòng trong documents với
text_origin='none' — biết là nó tồn tại, chỉ chưa tìm/trích được.
"""

import hashlib
import json
import logging
import uuid
from datetime import date

import psycopg

from app import config
from app.db.setup_database import apply_migrations
from app.ingest import download_moj_documents as moj
from app.ingest.split_articles import PARSER_VERSION, Article, split_html_into_articles
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _citation_numbers(articles: list[Article]) -> list[str]:
    """Số Điều dùng để trích dẫn, phân biệt Điều của văn bản kèm theo.

    Quyết định "ban hành kèm theo Quy chế" có Điều 1–3 của quyết định rồi Điều 1… của quy chế
    → hai "Điều 1" trong cùng văn bản. Khi số Điều lặp lại, coi như sang văn bản kèm theo.
    Điều của phần kèm theo lưu so = "QC1.5" (Điều 5 của văn bản kèm theo thứ nhất).
    """
    numbers, attached_part, seen = [], 0, set()
    for a in articles:
        if a.number in seen:
            attached_part, seen = attached_part + 1, set()
        seen.add(a.number)
        numbers.append(f"QC{attached_part}.{a.number}" if attached_part else a.number)
    return numbers


def save_document(conn: psycopg.Connection, doc: dict, source_url: str, raw_sha256: str) -> int:
    """Nạp một văn bản (xoá bản cũ nếu có) trong một transaction. Trả về số Điều đã nạp."""
    articles = split_html_into_articles(doc["documentContent"]["content"]) if moj.has_text_content(doc) else []
    doc_group = doc.get("docGroup") or ("CV" if doc.get("isAdministrativeDocument") else "UNKNOWN")

    with conn.transaction():
        conn.execute(
            "delete from documents where source = 'moj_gateway' and source_uuid = %s", (doc["id"],)
        )
        document_id = conn.execute(
            """
            insert into documents (source, source_uuid, source_url, so_hieu, loai, doc_group, co_quan,
                                   linh_vuc, ngay_ban_hanh, eff_from, eff_to, eff_status_code,
                                   is_consolidated, is_administrative, text_origin, raw_path,
                                   raw_sha256, parser_version)
            values ('moj_gateway', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                doc["id"], source_url, doc.get("docNum"), (doc.get("docType") or {}).get("name"), doc_group,
                doc.get("agencyName"), [f["name"] for f in doc.get("documentFields") or []] or None,
                _to_date(doc.get("issueDate")), _to_date(doc.get("effFrom")), _to_date(doc.get("effTo")),
                (doc.get("effStatus") or {}).get("code"), bool(doc.get("isConsolidatedDocument")),
                bool(doc.get("isAdministrativeDocument")), "native" if articles else "none",
                str((moj.MOJ_RAW_DIR / f"{doc['id']}.json").relative_to(config.PROJECT_ROOT)),
                raw_sha256, PARSER_VERSION,
            ),
        ).fetchone()[0]

        provision_rows = []  # một dòng cho mỗi Điều/khoản/điểm
        per_article = []  # (Điều, số trích dẫn, id provision của Điều, [(id provision, khoản/điểm)])
        ordinal = 0
        for article, citation_number in zip(articles, _citation_numbers(articles)):
            article_id = uuid.uuid4()
            ordinal += 1
            provision_rows.append((
                article_id, document_id, article.markup_id, "dieu", citation_number, article.title,
                None, ordinal, article.text, article.found_by,
            ))
            part_ids = []
            for part in article.clauses_and_points:
                part_id = uuid.uuid4()
                part_ids.append(part_id)
                ordinal += 1
                parent_id = part_ids[part.parent_clause_index] if part.parent_clause_index is not None else article_id
                provision_rows.append((
                    part_id, document_id, part.markup_id, part.level, part.number, None,
                    parent_id, ordinal, article.text_of(part), part.found_by,
                ))
            per_article.append((article, citation_number, article_id, list(zip(part_ids, article.clauses_and_points))))

        with conn.cursor() as cur:
            cur.executemany(
                """insert into provisions (id, document_id, provision_uuid, level, so, ten, parent_id,
                                           ordinal, text, parsed_by)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                provision_rows,
            )
            # chunk tham chiếu provision của Điều → chèn sau khi provisions đã có.
            for article, citation_number, article_id, parts in per_article:
                chunk_id = cur.execute(
                    "insert into chunks (document_id, dieu_provision_id, text) values (%s, %s, %s) returning id",
                    (document_id, article_id, article.text),
                ).fetchone()[0]
                position_rows = [(chunk_id, article_id, "dieu", citation_number, 0, len(article.text))]
                position_rows += [(chunk_id, pid, p.level, p.number, p.start, p.end) for pid, p in parts]
                cur.executemany(
                    """insert into chunk_positions (chunk_id, provision_id, level, so, char_start, char_end)
                       values (%s, %s, %s, %s, %s, %s)""",
                    position_rows,
                )
    return len(articles)


def save_documents_to_database() -> StageReport:
    """Nạp mọi văn bản thuế mới hoặc đã đổi. Mỗi văn bản một transaction riêng."""
    report = StageReport("database")
    apply_migrations()
    source_urls = moj.read_source_urls()
    # autocommit: mỗi conn.transaction() trong save_document là một transaction thật, commit ngay —
    # dừng giữa chừng thì các văn bản đã nạp vẫn còn.
    with psycopg.connect(config.DATABASE_CONNECTION, autocommit=True) as conn:
        loaded = dict(conn.execute(
            "select source_uuid, coalesce(raw_sha256, '') || '|' || coalesce(parser_version, '') "
            "from documents where source = 'moj_gateway'"
        ).fetchall())
        for path in sorted(moj.MOJ_RAW_DIR.glob("*.json")):
            try:
                body = path.read_bytes()
                doc = json.loads(body)["data"]
                if not moj.is_tax_document(doc):
                    continue
                raw_sha256 = hashlib.sha256(body).hexdigest()
                if loaded.get(doc["id"]) == f"{raw_sha256}|{PARSER_VERSION}":
                    report.count("khong_doi")
                    continue
                articles = save_document(conn, doc, source_urls.get(doc["id"], ""), raw_sha256)
                report.count("nap_lai" if doc["id"] in loaded else "nap_moi")
                report.count("so_dieu_da_nap", articles)
                report.count("van_ban_chua_tach_duoc", articles == 0)
            except Exception as e:  # một văn bản lỗi không được chặn các văn bản khác
                report.fail(path.name, e, log)
            done = sum(report.counts[k] for k in ("khong_doi", "nap_lai", "nap_moi")) + report.failure_count
            if done and done % 500 == 0:
                log.info("%d văn bản — %s", done, report.summary())
    log.info(report.summary())
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(save_documents_to_database().summary())


if __name__ == "__main__":
    main()

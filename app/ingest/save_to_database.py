"""Nạp văn bản thuế từ bản gốc trên đĩa vào database: documents → provisions → chunks → chunk_positions.

Chạy (sau download_moj_documents, cần .env; trong pipeline: công đoạn save_documents_to_database):
    python -m app.ingest.save_to_database

Chỉ nạp văn bản mới hoặc đã đổi: mỗi dòng documents ghi raw_sha256 (bản gốc) và parser_version
(bộ tách) — giống cả hai thì bỏ qua. Văn bản đổi thì xoá rồi nạp lại trong một transaction.
Một văn bản lỗi chỉ được ghi vào báo cáo, các văn bản khác vẫn nạp.
Văn bản không có Điều được cắt theo mục hoặc theo độ dài (split_articles) — cột level phân biệt.
JSON rỗng → chữ lấy từ file đính kèm (read_attachments): Word/RTF là 'native', PDF là 'ocr'.
Văn bản chưa có chữ (PDF scan, file chưa chuyển) vẫn có dòng trong documents với
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
from app.ingest import read_attachments
from app.ingest.check_document_quality import CheckResult, check_document
from app.ingest.split_articles import PARSER_VERSION, Article, TextLine, html_to_text_lines, split_into_articles
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


def read_document_text(doc: dict, attachment: read_attachments.Attachment | None
                       ) -> tuple[list[TextLine], list[Article], str]:
    """Chữ của văn bản: HTML của cổng; JSON rỗng thì file đính kèm. Trả về (các dòng, các Điều, text_origin).

    Chữ từ PDF, hoặc từ Word nhưng còn sót mã TCVN3, là 'ocr' — chỉ để tìm, không trích (quy tắc bất biến số 2).
    """
    if attachment is None:
        lines = html_to_text_lines(doc["documentContent"]["content"]) if moj.has_text_content(doc) else []
        origin = "native"
    else:
        lines = read_attachments.read_attachment_lines(attachment)
        garbled = attachment.text_origin == "native" and read_attachments.looks_garbled(lines)
        origin = "ocr" if attachment.text_origin == "ocr" or garbled else "native"
    articles = split_into_articles(lines, quotes_reliable=not (attachment and attachment.text_origin == "ocr"))
    return lines, articles, origin if articles else "none"


def save_document(conn: psycopg.Connection, doc: dict, source_url: str, raw_sha256: str,
                  articles: list[Article], text_origin: str, checks: list[CheckResult]) -> None:
    """Nạp một văn bản (xoá bản cũ nếu có) cùng kết quả kiểm chất lượng, trong một transaction."""
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
                                   raw_sha256, parser_version, tieu_de)
            values ('moj_gateway', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                doc["id"], source_url, doc.get("docNum"), (doc.get("docType") or {}).get("name"), doc_group,
                doc.get("agencyName"), [f["name"] for f in doc.get("documentFields") or []] or None,
                _to_date(doc.get("issueDate")), _to_date(doc.get("effFrom")), _to_date(doc.get("effTo")),
                (doc.get("effStatus") or {}).get("code"), bool(doc.get("isConsolidatedDocument")),
                bool(doc.get("isAdministrativeDocument")), text_origin,
                str((moj.MOJ_RAW_DIR / f"{doc['id']}.json").relative_to(config.PROJECT_ROOT)),
                raw_sha256, PARSER_VERSION, (doc.get("title") or "").strip() or None,
            ),
        ).fetchone()[0]

        provision_rows = []  # một dòng cho mỗi Điều/khoản/điểm
        per_article = []  # (Điều, số trích dẫn, id provision của Điều, [(id provision, khoản/điểm)])
        ordinal = 0
        for article, citation_number in zip(articles, _citation_numbers(articles)):
            article_id = uuid.uuid4()
            ordinal += 1
            provision_rows.append((
                article_id, document_id, article.markup_id, article.level, citation_number, article.title,
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
                "insert into document_checks (document_id, check_name, passed, severity, detail) values (%s, %s, %s, %s, %s)",
                [(document_id, c.name, c.passed, c.severity, c.detail or None) for c in checks],
            )
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
                position_rows = [(chunk_id, article_id, article.level, citation_number, 0, len(article.text))]
                position_rows += [(chunk_id, pid, p.level, p.number, p.start, p.end) for pid, p in parts]
                cur.executemany(
                    """insert into chunk_positions (chunk_id, provision_id, level, so, char_start, char_end)
                       values (%s, %s, %s, %s, %s, %s)""",
                    position_rows,
                )


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
                # Băm cả file đính kèm: file mới tải hoặc mới chuyển .docx xong thì văn bản được nạp lại.
                attachment = None if moj.has_text_content(doc) else read_attachments.find_attachment(doc)
                raw_sha256 = hashlib.sha256(body + (attachment.source.read_bytes() if attachment else b"")).hexdigest()
                if loaded.get(doc["id"]) == f"{raw_sha256}|{PARSER_VERSION}":
                    report.count("khong_doi")
                    continue
                lines, articles, text_origin = read_document_text(doc, attachment)
                consolidated = doc.get("docGroup") == "VBHN"
                checks = check_document(lines, articles, _citation_numbers(articles), consolidated) if articles else []
                save_document(conn, doc, source_urls.get(doc["id"], ""), raw_sha256, articles, text_origin, checks)
                for check in checks:
                    report.count(f"truot_{check.name}", not check.passed)
                report.count("nap_lai" if doc["id"] in loaded else "nap_moi")
                report.count("so_dieu_da_nap", len(articles))
                report.count("van_ban_chua_tach_duoc", not articles)
                if attachment and articles:
                    report.count("chu_tu_file_word" if text_origin == "native" else "chu_tu_file_chi_de_tim")
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

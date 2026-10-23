"""Kiểm chất lượng từng văn bản bằng bất biến chung (docs/architecture.md, Bốn lớp giữ dữ liệu sạch — lớp 2).

Không nhận dạng từng kiểu lỗi: kiểm điều mà mọi văn bản đúng đều phải thoả, nên lỗi kiểu mới cũng bị chặn.
  ma_chu         chữ không còn mã TCVN3 / ký tự hỏng                     trượt → cách ly
  thu_tu_de_muc  Điều / mục đánh số liên tục, không có đề mục bị bỏ        trượt → cách ly (văn bản hợp nhất:
                 cảnh báo — số Điều nhảy thường là Điều bị bãi bỏ đã bỏ khỏi bản hợp nhất)
  do_phu         phần thân văn bản nằm trong Điều / mục                  trượt → cảnh báo
  doan_qua_dai   không đoạn tìm kiếm nào quá dài                          trượt → cảnh báo
Cách ly: vẫn tìm được, không được trích, nằm trong danh sách chờ xem tay. Đã xem tay và ghi "đúng" vào
document_reviews (gắn với raw_sha256) thì hết cách ly — bản gốc đổi thì phải xem lại.

Chạy (trong pipeline: chạy bên trong công đoạn database_documents):
    python -m app.ingest.check_document_quality                          danh sách văn bản đang cách ly
    python -m app.ingest.check_document_quality --da-xem <mã> dung|sai "ghi chú"
                                                                         ghi kết quả xem tay (mã = source_uuid)
    python -m app.ingest.check_document_quality --check                  bài tự kiểm
"""

import re
import sys
from dataclasses import dataclass

import psycopg

from app import config
from app.ingest.read_attachments import TCVN3_SIGNATURE
from app.ingest.split_articles import (
    ROMAN_SECTION_HEADING, SIGNATURE_BLOCK, Article, TextLine, _roman_to_int, split_into_articles,
)

QUARANTINE = "cach_ly"
WARNING = "canh_bao"
MIN_BODY_COVERAGE = 0.9  # docs/danh-gia.md mục 2
MAX_PIECE_CHARS = 20000  # đoạn dài hơn làm tìm kiếm và ngữ cảnh model kém
LEADING_NUMBER = re.compile(r"(\d+)")
# Dòng trông như đề mục La Mã viết hoa ("III. TỔ CHỨC THỰC HIỆN") — để đếm đề mục không được nhận.
ROMAN_HEADING_LIKE = re.compile(r"^[IVXL]+\s?[.\-/)]\s*[A-ZĐÀ-Ỹ]{2}")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    severity: str  # QUARANTINE | WARNING
    detail: str


def check_encoding(lines: list[TextLine]) -> CheckResult:
    bad = [l.text for l in lines if "�" in l.text or sum(c in TCVN3_SIGNATURE for c in l.text) >= 2]
    return CheckResult("ma_chu", not bad, QUARANTINE,
                       f"{len(bad)} dòng còn mã TCVN3 / ký tự hỏng, ví dụ: {bad[0][:80]!r}" if bad else "")


def _number_value(article: Article) -> tuple[str, int] | None:
    """(nhóm đánh số, số thứ tự) — 'B.II' → ('B', 2); '9a' → ('', 9); 'QC1.5' → ('QC1', 5)."""
    group, _, number = article.number.rpartition(".")
    if article.level == "muc" and re.fullmatch(r"[IVXL]+", number):
        return group, _roman_to_int(number)
    match = LEADING_NUMBER.match(number)
    return (group, int(match[1])) if match else None


def check_numbering(articles: list[Article], citation_numbers: list[str], lines: list[TextLine],
                    consolidated: bool = False) -> CheckResult:
    """Số Điều / mục tăng đều từng bước trong mỗi nhóm; mục La Mã viết hoa nào trong thân văn bản cũng phải được nhận."""
    problems = []
    previous: dict[str, int] = {}
    for article, citation in zip(articles, citation_numbers):
        if article.level == "doan":
            continue
        value = _number_value(Article(citation, None, None, "", level=article.level))
        if value is None:
            continue
        group, number = value
        last = previous.get(group)
        # "9a" sau "9" cùng số → hợp lệ; còn lại phải đúng số kế tiếp (nhóm mới bắt đầu từ 1).
        if (last is None and number != 1) or (last is not None and number not in (last, last + 1)):
            problems.append(f"{citation} sau {last if last is not None else 'đầu nhóm'}")
        previous[group] = number
    if articles and articles[0].level == "muc":
        headings = {a.lines[0] for a in articles}
        start = next((i for i, l in enumerate(lines) if l.text == articles[0].lines[0]), 0)
        for line in lines[start:]:
            if SIGNATURE_BLOCK.match(line.text):
                break
            if ROMAN_HEADING_LIKE.match(line.text) and line.text not in headings:
                problems.append(f"đề mục không được nhận: {line.text[:50]!r}")
    return CheckResult("thu_tu_de_muc", not problems, WARNING if consolidated else QUARANTINE,
                       f"{len(problems)} chỗ: " + "; ".join(problems[:5]) if problems else "")


def check_coverage(articles: list[Article], lines: list[TextLine]) -> CheckResult:
    """Phần thân — từ đề mục đầu tiên tới khối chữ ký — phải nằm trong Điều / mục (phần mở đầu không tính)."""
    if not articles:
        return CheckResult("do_phu", True, WARNING, "")
    texts = [l.text for l in lines]
    start = next((i for i, t in enumerate(texts) if t == articles[0].lines[0]), 0)
    end = next((i for i in range(start, len(texts)) if SIGNATURE_BLOCK.match(texts[i])), len(texts))
    inside = {line for article in articles for line in article.lines}
    body = texts[start:end]
    total = sum(map(len, body))
    covered = sum(len(t) for t in body if t in inside)
    share = covered / total if total else 1.0
    return CheckResult("do_phu", share >= MIN_BODY_COVERAGE, WARNING, f"{share:.0%} phần thân nằm trong Điều / mục")


def check_piece_length(articles: list[Article]) -> CheckResult:
    longest = max((len(a.text) for a in articles), default=0)
    return CheckResult("doan_qua_dai", longest <= MAX_PIECE_CHARS, WARNING, f"đoạn dài nhất {longest} ký tự")


def check_document(lines: list[TextLine], articles: list[Article], citation_numbers: list[str],
                   consolidated: bool = False) -> list[CheckResult]:
    """`consolidated`: văn bản hợp nhất — thứ tự đề mục chỉ cảnh báo."""
    return [
        check_encoding(lines),
        check_numbering(articles, citation_numbers, lines, consolidated),
        check_coverage(articles, lines),
        check_piece_length(articles),
    ]


QUARANTINE_LIST_SQL = """
    select d.source_uuid, d.so_hieu, d.text_origin, q.reasons
    from quarantined_documents q join documents d on d.id = q.document_id
    order by d.text_origin, d.ngay_ban_hanh desc nulls last"""


def quarantine_list() -> list[tuple[str, str, str, str]]:
    """(mã, số hiệu, nguồn chữ, lý do) của văn bản đang cách ly — hàng đợi xem tay."""
    with psycopg.connect(config.DATABASE_CONNECTION) as conn:
        return conn.execute(QUARANTINE_LIST_SQL).fetchall()


def record_review(source_uuid: str, verdict: str, note: str | None) -> str:
    """Ghi kết quả xem tay cho bản gốc hiện tại của văn bản. Trả về số hiệu."""
    with psycopg.connect(config.DATABASE_CONNECTION) as conn:
        row = conn.execute("select source, raw_sha256, so_hieu from documents where source_uuid = %s",
                           (source_uuid,)).fetchone()
        if row is None:
            raise SystemExit(f"Không có văn bản mã {source_uuid}")
        conn.execute(
            """insert into document_reviews (source, source_uuid, raw_sha256, verdict, note) values (%s, %s, %s, %s, %s)
               on conflict (source, source_uuid, raw_sha256) do update set verdict = excluded.verdict,
                   note = excluded.note, reviewed_at = now()""",
            (row[0], source_uuid, row[1], verdict, note),
        )
        return row[2]


def self_check() -> None:
    def lines_of(*texts: str) -> list[TextLine]:
        return [TextLine(t) for t in texts]

    good = lines_of("THÔNG TƯ", "Điều 1. Phạm vi", "1. Khoản một", "Điều 2. Đối tượng", "Điều 2a. Bổ sung",
                    "Điều 3. Hiệu lực", "Nơi nhận:")
    articles = split_into_articles(good)
    results = {r.name: r for r in check_document(good, articles, [a.number for a in articles])}
    assert all(r.passed for r in results.values()), results

    gap = lines_of("Điều 1. A", "Điều 2. B", "Điều 5. C", "Điều 1. Quy chế kèm theo")
    articles = split_into_articles(gap)
    result = check_numbering(articles, ["1", "2", "5", "QC1.1"], gap)
    assert not result.passed and "5 sau 2" in result.detail and "QC1.1" not in result.detail, result
    assert result.severity == QUARANTINE
    consolidated = check_numbering(articles, ["1", "2", "5", "QC1.1"], gap, consolidated=True)
    assert not consolidated.passed and consolidated.severity == WARNING, "văn bản hợp nhất: chỉ cảnh báo"

    sections = lines_of("I. PHẠM VI", "chữ", "II. MỨC THUẾ", "chữ", "III. KÊ KHAI", "IV. GIẢM THUẾ", "VI. XỬ LÝ",
                        "chữ", "III. TỔ CHỨC THỰC HIỆN", "TM. BỘ TÀI CHÍNH")
    articles = split_into_articles(sections)
    result = check_numbering(articles, [a.number for a in articles], sections)
    assert not result.passed and "VI sau 4" in result.detail and "TỔ CHỨC THỰC HIỆN" in result.detail, result

    assert not check_encoding(lines_of("Bé tµi chÝnh quy ®Þnh")).passed
    assert check_encoding(lines_of("Bộ Tài chính, § 3")).passed
    assert not check_coverage(split_into_articles(lines_of("I. A", "x", "II. B")) [:1],
                              lines_of("I. A", "x", "II. B", "y" * 50)).passed
    print("PASS")


def main() -> None:
    if "--da-xem" in sys.argv:
        i = sys.argv.index("--da-xem")
        source_uuid, verdict = sys.argv[i + 1], sys.argv[i + 2]
        if verdict not in ("dung", "sai"):
            raise SystemExit("Kết quả phải là 'dung' hoặc 'sai'")
        print("Đã ghi:", record_review(source_uuid, verdict, sys.argv[i + 3] if len(sys.argv) > i + 3 else None))
        return
    rows = quarantine_list()
    for source_uuid, so_hieu, origin, reasons in rows:
        print(f"{source_uuid}  {so_hieu or '(không số)':<24} {origin:<6} {reasons[:150]}")
    print(f"{len(rows)} văn bản đang cách ly")


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

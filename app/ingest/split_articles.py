"""Tách văn bản thành Điều / khoản / điểm.

Tên trong code: Điều = article, khoản = clause, điểm = point.

Một bộ tách duy nhất, theo dòng chữ: "Điều 5." mở Điều, "1." mở khoản, "a)" mở điểm.
Markup prov-article/prov-clause/prov-item của cổng JSON không đầy đủ (TT 18/2026: 4/9 Điều),
nên không dựa vào nó để tách — chỉ dùng để gắn mã markup khi dòng đó có.

Mỗi Điều ra một đoạn tìm kiếm (text = các dòng nối bằng "\\n"), kèm vị trí ký tự của
từng khoản/điểm bên trong — đúng thứ bảng chunks + chunk_positions cần.

Chạy:  python -m app.ingest.split_articles --check
"""

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Tăng mỗi khi đổi cách tách: save_to_database thấy phiên bản khác thì nạp lại mọi văn bản.
PARSER_VERSION = "2026-10-02"

# ---------------------------------------------------------------- HTML → các dòng chữ


@dataclass
class TextLine:
    text: str
    markup_class: str | None = None  # 'prov-article' | 'prov-clause' | 'prov-item' | ...
    markup_id: str | None = None


class _HtmlToTextLines(HTMLParser):
    LINE_BREAKING_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
    IGNORED_TAGS = {"style", "script", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[TextLine] = []
        self.current_text: list[str] = []
        self.pending_markup: tuple[str | None, str | None] = (None, None)
        self.ignored_depth = 0

    def end_line(self) -> None:
        text = " ".join("".join(self.current_text).split())
        if text:
            self.lines.append(TextLine(unicodedata.normalize("NFC", text), *self.pending_markup))
            self.pending_markup = (None, None)  # markup chỉ thuộc dòng đầu của thẻ <p>
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORED_TAGS:
            self.ignored_depth += 1
        elif tag in self.LINE_BREAKING_TAGS:
            self.end_line()
            a = dict(attrs)
            if (a.get("class") or "").startswith("prov-"):
                self.pending_markup = (a["class"].split()[0], a.get("id"))
        elif tag == "td":
            self.current_text.append(" ")

    def handle_endtag(self, tag):
        if tag in self.IGNORED_TAGS:
            self.ignored_depth = max(0, self.ignored_depth - 1)
        elif tag in self.LINE_BREAKING_TAGS:
            self.end_line()

    def handle_data(self, data):
        if not self.ignored_depth:
            self.current_text.append(data)


def html_to_text_lines(html: str) -> list[TextLine]:
    converter = _HtmlToTextLines()
    converter.feed(html)
    converter.close()
    converter.end_line()
    return converter.lines


# ---------------------------------------------------------------- các dòng → Điều

ARTICLE_HEADING = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*[.:]?\s*(.*)$")
# Văn bản cũ còn viết "2)", "2-" cho khoản và "b/", "b." cho điểm.
CLAUSE_START = re.compile(r"^(\d+)\s?[.)\-](?!\d)\s*\S")
LETTER_POINT_START = re.compile(r"^([a-zđ])\s?[)/.]\s*\S")
NUMBERED_POINT_START = re.compile(r"^(\d+\.\d+)\.?\s+\S")  # "5.3" — điểm đánh số, gặp ở thông tư
# Dòng kết thúc Điều đang mở: đề mục cấp trên, phụ lục, câu thông qua. Đoạn trích dẫn có thể
# chứa đề mục ("Chương II" của luật được sửa) nên chỉ xét khi không ở trong ngoặc kép.
ENDS_ARTICLE = re.compile(
    r"^(Chương|CHƯƠNG|Mục|MỤC|Phần|PHẦN|Tiểu mục)\s+[\dIVXLC]+\b"
    r"|^PHỤ LỤC\b"
    r"|^(Luật|Bộ luật|Pháp lệnh|Nghị quyết) này (đã )?được .{0,120}thông qua"
)
# Khối nơi nhận / chữ ký không bao giờ nằm trong đoạn trích → luôn đóng Điều, kể cả khi một
# ngoặc kép gõ sai khiến bộ tách tưởng vẫn đang trong đoạn trích.
SIGNATURE_BLOCK = re.compile(r"^(Nơi nhận|NƠI NHẬN)\b|^(TM|KT|Q|TL|TUQ)\.\s")
# Thứ tự điểm theo bảng chữ cái tiếng Việt dùng trong văn bản (không có f, j, w, z).
POINT_LETTER_ORDER = "abcdđeghiklmnopqrstuvxy"


@dataclass
class ClauseOrPoint:
    """Khoản hoặc điểm, với vị trí [start, end) trong text của Điều chứa nó."""

    level: str  # 'khoan' | 'diem' — đúng giá trị cột provisions.level
    number: str  # '4' | 'a' | '5.3'
    start: int
    end: int
    parent_clause_index: int | None  # vị trí khoản cha trong Article.clauses_and_points; None = cha là Điều
    markup_id: str | None
    found_by: str  # 'markup' | 'regex' — đúng giá trị cột provisions.parsed_by


@dataclass
class Article:
    number: str  # '13' | '9a'
    title: str | None
    markup_id: str | None
    found_by: str
    lines: list[str] = field(default_factory=list)
    clauses_and_points: list[ClauseOrPoint] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def text_of(self, part: ClauseOrPoint) -> str:
        return self.text[part.start : part.end]


def _allowed_next_letters(previous: str | None) -> set[str]:
    if previous is None:
        return {"a"}
    if previous == "d":
        return {"đ", "e"}  # văn bản cũ không dùng điểm "đ"
    i = POINT_LETTER_ORDER.find(previous)
    return {POINT_LETTER_ORDER[i + 1]} if 0 <= i < len(POINT_LETTER_ORDER) - 1 else set()


def _quote_balance(text: str) -> int:
    """Số ngoặc kép mở trừ số đóng. Ngoặc gõ lẫn kiểu “…" có thật → '"' cũng tính là dấu đóng."""
    return text.count("“") - text.count("”") - text.count('"')


def split_into_articles(lines: list[TextLine]) -> list[Article]:
    """Các dòng chữ → danh sách Điều, mỗi Điều kèm khoản/điểm bên trong.

    Khoản/điểm chỉ được nhận khi đúng thứ tự (khoản 3 phải sau khoản 2, điểm c sau điểm b).
    Một dòng "2." lạc chỗ — ví dụ trong bảng — vì vậy thành chữ thường của phần đang mở
    thay vì mở khoản giả. Đoạn trích trong ngoặc kép “…” ở lại nguyên trong khoản đang mở.
    """
    articles: list[Article] = []
    article: Article | None = None  # Điều đang mở
    open_clause: int | None = None  # vị trí khoản đang mở trong article.clauses_and_points
    open_point: int | None = None
    text_length = 0  # độ dài text của Điều đang mở tính đến hết dòng trước
    open_quotes = 0  # số ngoặc kép “ đang mở chưa đóng

    def markup_if_labelled(line: TextLine, expected_class: str) -> tuple[str | None, str]:
        return (line.markup_id, "markup") if line.markup_class == expected_class else (None, "regex")

    for line in lines:
        text = line.text.strip()
        # Đang ở giữa đoạn trích trong ngoặc kép (văn bản sửa đổi trích nguyên Điều mới,
        # có thể nhiều Điều, nhiều dòng): mọi dòng bên trong — kể cả "Điều 10.", "1.",
        # "a)" — là chữ của đoạn trích, không mở Điều/khoản/điểm mới.
        # Dòng đã được biên tập viên đánh dấu là Điều thì chắc chắn không nằm trong đoạn trích —
        # chặn trường hợp một ngoặc gõ sai nuốt hết phần còn lại của văn bản.
        if line.markup_class == "prov-article":
            open_quotes = 0
        inside_quote = article is not None and open_quotes > 0
        open_quotes = max(0, open_quotes + _quote_balance(text))

        if SIGNATURE_BLOCK.match(text) or (not inside_quote and ENDS_ARTICLE.match(text)):
            article = None
            open_quotes = 0
            continue
        if not inside_quote and (m := ARTICLE_HEADING.match(text)):
            markup_id, found_by = markup_if_labelled(line, "prov-article")
            article = Article(number=m[1], title=m[2].strip() or None, markup_id=markup_id, found_by=found_by)
            articles.append(article)
            open_clause = open_point = None
            open_quotes = max(0, _quote_balance(text))
            article.lines.append(text)
            text_length = len(text)
            continue
        if article is None:
            open_quotes = 0
            continue

        start = text_length + 1  # +1 cho "\n" nối với dòng trước
        parts = article.clauses_and_points
        current_clause = parts[open_clause] if open_clause is not None else None
        current_point = parts[open_point] if open_point is not None else None
        clauses_so_far = sum(p.level == "khoan" for p in parts)

        if inside_quote:
            pass
        elif (m := CLAUSE_START.match(text)) and int(m[1]) == clauses_so_far + 1:
            markup_id, found_by = markup_if_labelled(line, "prov-clause")
            parts.append(ClauseOrPoint("khoan", m[1], start, 0, None, markup_id, found_by))
            open_clause, open_point = len(parts) - 1, None
        elif (m := LETTER_POINT_START.match(text)) and m[1] in _allowed_next_letters(
            current_point.number if current_point else None
        ):
            markup_id, found_by = markup_if_labelled(line, "prov-item")
            parts.append(ClauseOrPoint("diem", m[1], start, 0, open_clause, markup_id, found_by))
            open_point = len(parts) - 1
        elif (
            (m := NUMBERED_POINT_START.match(text))
            and current_clause
            and m[1].split(".")[0] == current_clause.number
        ):
            markup_id, found_by = markup_if_labelled(line, "prov-item")
            parts.append(ClauseOrPoint("diem", m[1], start, 0, open_clause, markup_id, found_by))
            open_point = len(parts) - 1

        article.lines.append(text)
        text_length = start + len(text)
        # Dòng này kéo dài khoản và điểm đang mở tới hết dòng.
        for i in {open_clause, open_point} - {None}:
            parts[i].end = text_length

    return articles


def split_html_into_articles(html: str) -> list[Article]:
    return split_into_articles(html_to_text_lines(html))


# ---------------------------------------------------------------- tự kiểm


def self_check() -> None:
    html = """<html><head><style>p{}</style></head><body>
    <p>QUỐC HỘI</p><p>1. Dòng đánh số ở phần mở đầu không thuộc Điều nào</p>
    <p class="prov-chapter">Chương I<br>QUY ĐỊNH CHUNG</p>
    <p id="u-d13" class="prov-article"><strong>Điều 13. Xử phạt hành vi chậm nộp hồ sơ khai thuế</strong></p>
    <p id="u-k1" class="prov-clause">1. Phạt cảnh cáo đối với hành vi nộp hồ sơ quá hạn từ 01 ngày đến 05 ngày.</p>
    <p>4. Phạt tiền từ 8.000.000 đồng đến 15.000.000 đồng đối với một trong các hành vi sau đây:</p>
    <p>2. Phạt tiền từ 2.000.000 đồng đến 5.000.000 đồng.</p>
    <p class="prov-item" id="u-a">a) Nộp hồ sơ khai thuế quá thời hạn từ 61 ngày đến 90 ngày;</p>
    <p>b) Không nộp hồ sơ khai thuế;</p>
    <p>d) dòng lạc thứ tự</p>
    <p>Điều 14. Sửa đổi</p>
    <p>1. Sửa đổi khoản 2 như sau:</p>
    <p>“Điều 9. Thuế suất</p><p>1. Thuế suất 5%.</p><p>2. Thuế suất 10%.</p>
    <p>Điều 10. Hoàn thuế</p><p>3. Trong đoạn trích</p><p>a) Trong đoạn trích.”</p>
    <p>2. Bãi bỏ Điều 12.</p>
    <p>3. Sửa đổi Điều 20: “ngoặc gõ sai không bao giờ đóng</p>
    <p>Nơi nhận:</p><p>1. Văn phòng Chính phủ</p>
    <p>QUY CHẾ</p><p>Điều 1: Phạm vi</p><p>Quy chế này quy định ...</p>
    <p>5. Dòng 5 không thể là khoản đầu</p>
    <p>Điều 2. Hướng dẫn</p><p>1. Khoản một</p><p>1.1. Điểm số một</p><p>1.2. Điểm số hai</p>
    </body></html>"""
    articles = split_html_into_articles(html)
    assert [a.number for a in articles] == ["13", "14", "1", "2"], [a.number for a in articles]

    a13 = articles[0]
    assert a13.title == "Xử phạt hành vi chậm nộp hồ sơ khai thuế" and a13.markup_id == "u-d13"
    assert a13.found_by == "markup"
    # "4." lạc thứ tự không mở khoản; "2." thì có. "d)" sau "b)" không mở điểm.
    assert [(p.level, p.number) for p in a13.clauses_and_points] == [
        ("khoan", "1"), ("khoan", "2"), ("diem", "a"), ("diem", "b")]
    k1, k2, pa, pb = a13.clauses_and_points
    assert k1.markup_id == "u-k1" and k1.found_by == "markup" and k2.found_by == "regex"
    assert a13.text_of(k1).startswith("1. Phạt cảnh cáo") and "8.000.000" in a13.text_of(k1), "dòng lạc ở lại khoản 1"
    assert a13.text_of(k2).startswith("2. Phạt tiền") and a13.text_of(k2).endswith("dòng lạc thứ tự")
    assert pa.parent_clause_index == 1 and pa.markup_id == "u-a" and a13.text_of(pa).endswith("90 ngày;")
    assert a13.text_of(pb) == "b) Không nộp hồ sơ khai thuế;\nd) dòng lạc thứ tự"
    assert "Chương" not in a13.text and "QUY ĐỊNH CHUNG" not in a13.text

    a14 = articles[1]
    assert [p.number for p in a14.clauses_and_points] == ["1", "2", "3"], "Điều/khoản/điểm trong ngoặc kép không mở phần mới"
    k1 = a14.text_of(a14.clauses_and_points[0])
    assert "“Điều 9. Thuế suất" in k1 and "Điều 10. Hoàn thuế" in k1 and k1.endswith("a) Trong đoạn trích.”")
    assert a14.text_of(a14.clauses_and_points[1]) == "2. Bãi bỏ Điều 12."
    assert "Văn phòng Chính phủ" not in a14.text, "Nơi nhận đóng Điều, kể cả khi ngoặc kép chưa đóng"

    q1, q2 = articles[2], articles[3]
    assert q1.title == "Phạm vi" and q1.clauses_and_points == [], "Điều 1: dạng dấu hai chấm; '5.' không mở khoản"
    assert [(p.level, p.number, p.parent_clause_index) for p in q2.clauses_and_points] == [
        ("khoan", "1", None), ("diem", "1.1", 0), ("diem", "1.2", 0)]

    # Mọi vị trí phải cắt đúng ranh giới dòng.
    for a in articles:
        for p in a.clauses_and_points:
            s = a.text_of(p)
            assert s == s.strip() and a.text[p.start - 1] == "\n", (a.number, p)
    print("PASS")


if __name__ == "__main__":
    if "--check" in sys.argv:
        self_check()

"""Tách văn bản thành Điều / khoản / điểm.

Tên trong code: Điều = article, khoản = clause, điểm = point.

Một bộ tách duy nhất, theo dòng chữ: "Điều 5." mở Điều, "1." mở khoản, "a)" mở điểm.
Markup prov-article/prov-clause/prov-item của cổng JSON không đầy đủ (TT 18/2026: 4/9 Điều),
nên không dựa vào nó để tách — chỉ dùng để gắn mã markup khi dòng đó có.

Mỗi Điều ra một đoạn tìm kiếm (text = các dòng nối bằng "\\n"), kèm vị trí ký tự của
từng khoản/điểm bên trong — đúng thứ bảng chunks + chunk_positions cần.

Văn bản không có Điều (thông tư cũ) cắt theo đề mục lớn nhất (docs/architecture.md, Dữ liệu):
mục La Mã "I." (phần chữ "A." phía trên ghi vào số mục: "B.II"), không có thì mục số "1.",
không có cả hai thì cắt theo độ dài. Kết quả vẫn là Article, với level 'muc' hoặc 'doan'.

Chạy:  python -m app.ingest.split_articles --check
"""

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Tăng mỗi khi đổi cách tách: save_to_database thấy phiên bản khác thì nạp lại mọi văn bản.
PARSER_VERSION = "2026-10-22h"

# ---------------------------------------------------------------- HTML → các dòng chữ


@dataclass
class TextLine:
    text: str
    markup_class: str | None = None  # 'prov-article' | 'prov-clause' | 'prov-item' | ...
    markup_id: str | None = None


class _HtmlToTextLines(HTMLParser):
    LINE_BREAKING_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
    IGNORED_TAGS = {"style", "script", "head", "title"}

    def __init__(self, skipped_div_classes: tuple[str, ...] = ()) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[TextLine] = []
        self.current_text: list[str] = []
        self.pending_markup: tuple[str | None, str | None] = (None, None)
        self.ignored_depth = 0
        self.skipped_div_classes = set(skipped_div_classes)
        self.skipped_div_depth = 0  # > 0: đang trong một <div> bị bỏ (đếm cả div lồng bên trong)

    def end_line(self) -> None:
        text = " ".join("".join(self.current_text).split())
        if text:
            self.lines.append(TextLine(unicodedata.normalize("NFC", text), *self.pending_markup))
            self.pending_markup = (None, None)  # markup chỉ thuộc dòng đầu của thẻ <p>
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "div" and (self.skipped_div_depth or (dict(attrs).get("class") or "") in self.skipped_div_classes):
            self.skipped_div_depth += 1
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
        if tag == "div" and self.skipped_div_depth:
            self.skipped_div_depth -= 1

    def handle_data(self, data):
        if not self.ignored_depth and not self.skipped_div_depth:
            self.current_text.append(data)


def html_to_text_lines(html: str, skipped_div_classes: tuple[str, ...] = ()) -> list[TextLine]:
    """skipped_div_classes: bỏ chữ trong <div class="…"> — XHTML của Tika để header/footer trang trong
    div class="header" / "footer" (read_attachments)."""
    converter = _HtmlToTextLines(skipped_div_classes)
    converter.feed(html)
    converter.close()
    converter.end_line()
    return converter.lines


# ---------------------------------------------------------------- các dòng → Điều

# Đề mục Điều: "Điều 5." / "Điều 5:" / "Điều 5 Tên viết hoa" / "Điều 5" đứng một mình. Câu dẫn chiếu đầu dòng
# "Điều 179 của Luật Thi hành án…" (chú thích văn bản hợp nhất, gặp 22/10/2026) không phải đề mục: sau số là chữ thường.
# Dấu chấm sau số Điều có khi hỏng thành một ký tự dính liền số: "Điều 4ể Hàng hóa GIC" (201/2015/TT-BTC, HTML
# của cổng) — vẫn là đề mục. Phân biệt với câu dẫn chiếu: câu dẫn chiếu có khoảng trắng trước chữ thường.
ARTICLE_HEADING = re.compile(r"^Điều\s+(\d+[a-zđ]?)(\s*)([.:]?)\s*(.*)$")
# Sau số Điều là tên một văn bản kèm số hiệu → câu dẫn chiếu ("Điều 7 Thông tư số 119/2014/TT-BTC…"), không phải tên Điều.
REFERENCED_DOCUMENT = re.compile(r"(Luật|Bộ luật|Pháp lệnh|Nghị quyết|Nghị định|Thông tư|Quyết định)\b[^.]{0,40}?\bsố\s*\d")


def match_article_heading(text: str) -> tuple[str, str | None] | None:
    """(số Điều, tên Điều) nếu dòng là đề mục Điều."""
    m = ARTICLE_HEADING.match(text)
    if not m:
        return None
    number, space, separator, rest = m[1], m[2], m[3], m[4]
    if not separator and rest[:1] in (",", ";"):
        # "Điều 7, Điều 8 của Nghị định…" — liệt kê dẫn chiếu; "Điều 1, Phạm vi điều chỉnh" (60/2011/TTLT) — đề mục
        title = rest[1:].strip()
        if not title or title.startswith("Điều") or title[:1].islower():
            return None
        return number, title
    if not separator and not space and rest:  # ký tự hỏng dính số thay cho dấu chấm ("4ể", "1-")
        return number, rest[1:].strip() or None
    if not separator and REFERENCED_DOCUMENT.match(rest):  # "Điều 7 Thông tư số 119/2014/TT-BTC sửa đổi…"
        return None
    words = rest.split(maxsplit=1)
    if not separator and len(words) == 2 and len(words[0]) == 1 and words[1][:1].isupper():
        return number, words[1]  # "Điều 21 ế Đăng ký thuế" (chữ PDF): ký tự hỏng đứng riêng, tên Điều viết hoa
    if not separator and rest[:1].islower():  # "Điều 179 của Luật…" — câu dẫn chiếu
        return None
    return number, rest.strip() or None
# Văn bản cũ còn viết "2)", "2-" cho khoản và "b/", "b." cho điểm.
CLAUSE_START = re.compile(r"^(\d+)\s?[.)\-](?!\d)\s*\S")
LETTER_POINT_START = re.compile(r"^([a-zđ])\s?[)/.]\s*\S")
NUMBERED_POINT_START = re.compile(r"^(\d+\.\d+)\.?\s+\S")  # "5.3" — điểm đánh số, gặp ở thông tư
# Dòng kết thúc Điều đang mở: đề mục cấp trên, phụ lục, câu thông qua. Đoạn trích dẫn có thể
# chứa đề mục ("Chương II" của luật được sửa) nên chỉ xét khi không ở trong ngoặc kép.
ENDS_ARTICLE = re.compile(
    r"^(Chương|CHƯƠNG|Mục|MỤC|Phần|PHẦN|Tiểu mục)\s+[\dIVXLC]+\b"
    r"|^PHỤ LỤC\b"
    # chú thích cuối của văn bản hợp nhất: "[20] Điều 44 của Luật An ninh mạng…" — không thuộc Điều nào
    r"|^\[\d+\]"
    r"|^(Luật|Bộ luật|Pháp lệnh|Nghị quyết) này (đã )?được .{0,120}thông qua"
)
# Khối nơi nhận / chữ ký không bao giờ nằm trong đoạn trích → luôn đóng Điều, kể cả khi một
# ngoặc kép gõ sai khiến bộ tách tưởng vẫn đang trong đoạn trích.
SIGNATURE_BLOCK = re.compile(r"^(Nơi nhận|NƠI NHẬN)\b|^(TM|KT|Q|TL|TUQ)\.\s")
# Thứ tự điểm theo bảng chữ cái tiếng Việt dùng trong văn bản (không có f, j, w, z).
POINT_LETTER_ORDER = "abcdđeghiklmnopqrstuvxy"
# Đề mục của văn bản không có Điều: "II- CĂN CỨ TÍNH THUẾ", "B. VỀ THUẾ PHÁT SINH".
ROMAN_SECTION_HEADING = re.compile(r"^([IVXL]+)\s?[.\-/)]\s*(\S.*)$")
PART_HEADING = re.compile(r"^([A-HĐKMN])\s?[.\-/)]\s+(\S.*)$")  # không có I, L, V, X — trùng số La Mã
PART_WORD_HEADING = re.compile(r"^(?:PHẦN|Phần)\s+([A-ZĐ])\b(.*)$")  # "Phần A", "PHẦN B - KHAI THUẾ"
# Thông tư 59/2007, 60/2007: Phần A, B, C, D, Đ, E, G, H, K, M, N — thứ tự chữ cái tiếng Việt, có khi bỏ chữ.
PART_ORDER = "ABCDĐEGHIKLMNOPQRSTUVXY"
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50}
# Trong văn bản không có Điều, "Mục II.3.a - …" là chữ của văn bản sửa đổi, không phải đề mục cấp trên
# → chỉ phụ lục đóng mục (ENDS_ARTICLE dùng cho văn bản có Điều).
ENDS_SECTION = re.compile(r"^PHỤ LỤC\b")
MAX_CHARS_PER_PIECE = 6000  # văn bản không có đề mục nào: cắt theo độ dài tại ranh giới dòng


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
    """Một Điều — hoặc, với văn bản không có Điều, một mục / một đoạn cắt theo độ dài."""

    number: str  # '13' | '9a' | mục: 'II' | 'B.II' (mục II phần B) | '3'
    title: str | None
    markup_id: str | None
    found_by: str
    level: str = "dieu"  # 'dieu' | 'muc' | 'doan' — đúng giá trị cột provisions.level
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


def _roman_to_int(numeral: str) -> int:
    values = [ROMAN_VALUES[c] for c in numeral]
    return sum(-v if v < following else v for v, following in zip(values, values[1:] + [0]))


@dataclass
class Heading:
    number: str
    title: str | None
    opens: bool = True  # False = đề mục cấp trên (phần A/B): chỉ đóng mục đang mở, không mở đoạn mới


class _ArticleHeadings:
    level, finds_clauses, ends = "dieu", True, ENDS_ARTICLE

    def reset(self) -> None:
        pass

    def match(self, text: str) -> Heading | None:
        found = match_article_heading(text)
        return Heading(*found) if found else None


class _RomanSectionHeadings:
    """Mục La Mã "I.", "II-" (kèm phần chữ "A.", "B." phía trên nếu có) — chỉ nhận khi đúng thứ tự."""

    level, finds_clauses, ends = "muc", True, ENDS_SECTION

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:  # sau khối chữ ký: văn bản kèm theo đánh số lại từ đầu
        self.part, self.last = None, 0

    def match(self, text: str) -> Heading | None:
        current = PART_ORDER.find(self.part) if self.part else -1
        # "Phần B" có chữ "Phần" → chắc là đề mục phần: chỉ cần đi sau phần trước (văn bản có khi bỏ chữ).
        if (m := PART_WORD_HEADING.match(text)) and PART_ORDER.find(m[1]) > current:
            self.part, self.last = m[1], 0
            return Heading(m[1], None, opens=False)
        # "B." trơn thì chặt hơn: viết hoa ("B. VỀ THUẾ PHÁT SINH"), đúng chữ kế tiếp, và "A." chỉ đứng trước
        # mục I — "A.", "B." viết thường hoặc bên trong một mục là ý liệt kê, không phải phần.
        if (m := PART_HEADING.match(text)) and m[2].isupper() and (
            (m[1] == "A" and self.part is None and self.last == 0)
            or (self.part is not None and PART_ORDER.find(m[1]) == current + 1)
        ):
            self.part, self.last = m[1], 0
            return Heading(m[1], m[2], opens=False)
        # Văn bản gốc có khi nhảy số (53-TC/TCT: IV → VI) → cho bỏ một số nếu tiêu đề viết hoa như đề mục;
        # dòng trong bảng ("V. Đô Thị loại V") thường viết thường.
        if (m := ROMAN_SECTION_HEADING.match(text)) and (
            (value := _roman_to_int(m[1])) == self.last + 1 or (value == self.last + 2 and self.last and m[2].isupper())
        ):
            self.last = value
            return Heading(f"{self.part}.{m[1]}" if self.part else m[1], m[2].strip(" .:") or None)
        return None


class _NumberedSectionHeadings:
    """Văn bản chỉ đánh "1.", "2." ở cấp cao nhất: mỗi số là một mục, "a)" bên trong là điểm."""

    level, finds_clauses, ends = "muc", False, ENDS_SECTION

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.last = 0

    def match(self, text: str) -> Heading | None:
        if (m := CLAUSE_START.match(text)) and int(m[1]) == self.last + 1:
            self.last += 1
            return Heading(m[1], None)
        return None


def split_into_articles(lines: list[TextLine], quotes_reliable: bool = True) -> list[Article]:
    """Các dòng chữ → danh sách Điều; văn bản không có Điều → mục La Mã, mục số, cuối cùng là đoạn theo độ dài.

    Một mục duy nhất chưa đủ để coi là cách chia của văn bản ("I." lẻ loi) → thử cách tiếp theo.
    quotes_reliable=False cho chữ PDF: ngoặc kép hay bị đọc sai, mất cân (đo 22/10/2026: 99/2016/TT-BTC mất 15 Điều).
    """
    for rules in (_ArticleHeadings(), _RomanSectionHeadings(), _NumberedSectionHeadings()):
        articles = _split(lines, rules, quotes_reliable)
        if articles and (rules.level == "dieu" or len(articles) >= 2):
            return articles
    return _split_by_length(lines)


def _split_by_length(lines: list[TextLine]) -> list[Article]:
    """Đoạn ≤ MAX_CHARS_PER_PIECE ký tự, cắt tại ranh giới dòng, dừng ở khối chữ ký."""
    pieces: list[Article] = []
    length = 0
    for line in lines:
        text = line.text.strip()
        if SIGNATURE_BLOCK.match(text):
            break
        if not pieces or length + 1 + len(text) > MAX_CHARS_PER_PIECE:
            pieces.append(Article(str(len(pieces) + 1), None, None, "regex", level="doan"))
            length = -1
        pieces[-1].lines.append(text)
        length += 1 + len(text)
    return pieces


def _split(lines: list[TextLine], rules, quotes_reliable: bool = True) -> list[Article]:
    """Các dòng chữ → danh sách Điều (hoặc mục), mỗi phần kèm khoản/điểm bên trong.

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
        # Sau Điều đầu tiên, ngoặc kép được theo dõi cả khi không có Điều nào đang mở: chú thích cuối của văn bản
        # hợp nhất (sau khối chữ ký) trích nguyên "“Điều 8. Trách nhiệm thực hiện…”" của văn bản sửa đổi (gặp
        # 22/10/2026, 27/2026/VBHN-NĐ-BTC). Phần mở đầu thì không — ngoặc gõ sai ở "Căn cứ…" không được nuốt Điều 1.
        inside_quote = (article is not None or (quotes_reliable and bool(articles))) and open_quotes > 0
        open_quotes = max(0, open_quotes + _quote_balance(text))

        if SIGNATURE_BLOCK.match(text):
            rules.reset()
        heading = None if inside_quote else rules.match(text)
        if SIGNATURE_BLOCK.match(text) or (not inside_quote and rules.ends.match(text)) or (heading and not heading.opens):
            article = None
            open_quotes = 0
            continue
        if heading:
            markup_id, found_by = markup_if_labelled(line, "prov-article")
            article = Article(heading.number, heading.title, markup_id, found_by, level=rules.level)
            articles.append(article)
            open_clause = open_point = None
            open_quotes = max(0, _quote_balance(text))
            article.lines.append(text)
            text_length = len(text)
            continue
        if article is None:
            if not (quotes_reliable and articles):
                open_quotes = 0
            continue

        start = text_length + 1  # +1 cho "\n" nối với dòng trước
        parts = article.clauses_and_points
        current_clause = parts[open_clause] if open_clause is not None else None
        current_point = parts[open_point] if open_point is not None else None
        clauses_so_far = sum(p.level == "khoan" for p in parts)

        if inside_quote:
            pass
        elif rules.finds_clauses and (m := CLAUSE_START.match(text)) and int(m[1]) == clauses_so_far + 1:
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
    <p>Điều 3 Hiệu lực thi hành</p><p>Điều 4ể Hàng hóa</p>
    <p>[20] Điều 44 của Luật An ninh mạng có quy định như sau:</p>
    <p>Điều 179 của Luật Thi hành án hình sự có hiệu lực kể từ ngày 01 tháng 7 năm 2026</p>
    <p>TM. CHÍNH PHỦ</p><p>Điều 7, Điều 8 của Nghị định số 102/2021/NĐ-CP quy định như sau:</p>
    <p>“Điều 7. Quy định chuyển tiếp</p><p>Điều 8. Trách nhiệm thực hiện</p><p>Hết đoạn trích.”</p>
    </body></html>"""
    articles = split_html_into_articles(html)
    assert [a.number for a in articles] == ["13", "14", "1", "2", "3", "4"], [a.number for a in articles]
    assert articles[4].title == "Hiệu lực thi hành" and articles[5].title == "Hàng hóa", "dấu chấm hỏng dính số"
    assert match_article_heading("Điều 9a. Bổ sung") == ("9a", "Bổ sung") and match_article_heading("Điều 4") == ("4", None)
    assert match_article_heading("Điều 21 ế Đăng ký thuế") == ("21", "Đăng ký thuế")
    assert match_article_heading("Điều 7, Điều 8 của Nghị định số 102/2021/NĐ-CP") is None
    assert match_article_heading("Điều 1, Phạm vi điều chỉnh") == ("1", "Phạm vi điều chỉnh")
    assert match_article_heading("Điều 7 Thông tư số 119/2014/TT-BTC sửa đổi, bổ sung") is None
    assert match_article_heading("Điều 3. Thông tư số 12/2010 hết hiệu lực") == ("3", "Thông tư số 12/2010 hết hiệu lực")
    assert match_article_heading("Điều 1- Nay ban hành") == ("1", "Nay ban hành")
    assert match_article_heading("Điều 3 c ủa Lu ật thuế") is None and match_article_heading("Điều 2 của Luật này.") is None
    assert "Luật An ninh mạng" not in articles[5].text, "chú thích cuối '[20] …' đóng Điều đang mở"

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

    # Văn bản không có Điều: phần chữ A/B + mục La Mã; mục đúng thứ tự mới được nhận.
    roman_html = """<p>THÔNG TƯ</p><p>Hướng dẫn thuế môn bài</p>
    <p>A. VỀ THUẾ MÔN BÀI</p><p>I. ĐỐI TƯỢNG NỘP THUẾ</p><p>1. Doanh nghiệp</p><p>2. Cá nhân kinh doanh</p>
    <p>a) hộ cá thể</p><p>b) nhóm kinh doanh</p>
    <p>II- MỨC THUẾ:</p><p>1. Bậc 1</p><p>V. Đô thị loại V</p><p>IV. Đô thị loại IV</p>
    <p>A. lệnh trong mục, không phải phần</p>
    <p>B. VỀ THUẾ PHÁT SINH</p><p>I. Phạm vi</p><p>Chữ của mục I phần B</p>
    <p>Mục II.3.a - Chi phí khấu hao được sửa như sau</p>
    <p>Phần Đ - HOÀN THUẾ</p><p>I. Hồ sơ hoàn thuế</p><p>Phần thu nhập tăng thêm không phải đề mục</p>
    <p>Phần K</p><p>I. Khiếu nại</p><p>III- TỔ CHỨC THỰC HIỆN</p>
    <p>Nơi nhận:</p><p>I. Biểu mẫu kèm theo</p><p>Chữ biểu mẫu</p>"""
    sections = split_html_into_articles(roman_html)
    assert [(s.level, s.number, s.title) for s in sections] == [
        ("muc", "A.I", "ĐỐI TƯỢNG NỘP THUẾ"), ("muc", "A.II", "MỨC THUẾ"), ("muc", "B.I", "Phạm vi"),
        ("muc", "Đ.I", "Hồ sơ hoàn thuế"), ("muc", "K.I", "Khiếu nại"), ("muc", "K.III", "TỔ CHỨC THỰC HIỆN"),
        ("muc", "I", "Biểu mẫu kèm theo"),
    ], [(s.number, s.title) for s in sections]
    a_i, a_ii, b_i, d_i = sections[:4]
    assert "Phần thu nhập tăng thêm" in d_i.text, "'Phần thu nhập' không phải đề mục phần"
    assert [(p.level, p.number, p.parent_clause_index) for p in a_i.clauses_and_points] == [
        ("khoan", "1", None), ("khoan", "2", None), ("diem", "a", 1), ("diem", "b", 1)]
    assert "V. Đô thị loại V" in a_ii.text and "lệnh trong mục" in a_ii.text, "đề mục sai thứ tự là chữ thường"
    assert "VỀ THUẾ PHÁT SINH" not in a_ii.text, "phần chữ mới đóng mục đang mở"
    assert b_i.text.endswith("được sửa như sau"), "'Mục II.3.a' trong văn bản không có Điều không đóng mục"

    numbered = split_html_into_articles(
        "<p>THÔNG TƯ</p><p>1- Đối tượng nộp thuế</p><p>a) Tổ chức</p><p>3. Lạc thứ tự</p>"
        "<p>2. Thuế suất 3%</p><p>1. Không mở lại</p><p>Nơi nhận:</p>")
    assert [(s.level, s.number) for s in numbered] == [("muc", "1"), ("muc", "2")]
    assert [(p.level, p.number) for p in numbered[0].clauses_and_points] == [("diem", "a")]
    assert numbered[1].text == "2. Thuế suất 3%\n1. Không mở lại", "trong mục số không tìm khoản"

    long_line = "x" * 4000
    pieces = split_html_into_articles(f"<p>LỆNH</p><p>{long_line}</p><p>{long_line}</p><p>TM. CHÍNH PHỦ</p><p>ký</p>")
    assert [(p.level, p.number, len(p.text)) for p in pieces] == [("doan", "1", 4005), ("doan", "2", 4000)]
    assert split_html_into_articles("") == []

    # Mọi vị trí phải cắt đúng ranh giới dòng.
    for a in articles + sections + numbered:
        for p in a.clauses_and_points:
            s = a.text_of(p)
            assert s == s.strip() and a.text[p.start - 1] == "\n", (a.number, p)
    print("PASS")


if __name__ == "__main__":
    if "--check" in sys.argv:
        self_check()

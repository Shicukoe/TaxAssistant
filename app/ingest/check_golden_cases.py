"""Bộ đo cố định: mỗi lỗi gặp thật là một ca, chạy trên văn bản thật (docs/architecture.md, Bốn lớp — lớp 3).

Sửa bộ tách (split_articles), bộ đọc file (read_attachments) hay phép kiểm chất lượng
(check_document_quality) → chạy lại cả bộ. Sửa ca mới không được làm hỏng ca cũ.
Gặp lỗi mới → thêm một ca ở đây TRƯỚC khi sửa code (ca phải trượt trước, đạt sau).

Cần bản gốc trong data/raw/ (không commit) và .docx đã chuyển trong data/converted/.
Chạy:  python -m app.ingest.check_golden_cases
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass

from app.ingest import download_moj_documents as moj
from app.ingest import read_attachments
from app.ingest.check_document_quality import CheckResult, check_document
from app.ingest.link_consolidated_documents import header_matches_number, plain_text, read_header_number
from app.ingest.save_to_database import _citation_numbers, read_document_text
from app.ingest.split_articles import Article, TextLine


@dataclass
class Loaded:
    doc: dict
    lines: list[TextLine]
    articles: list[Article]
    text_origin: str
    checks: dict[str, CheckResult]

    @property
    def numbers(self) -> list[str]:
        return _citation_numbers(self.articles)

    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def load(file_id: str) -> Loaded:
    """Đi đúng đường của save_to_database: JSON → (HTML hoặc file đính kèm) → Điều/mục → phép kiểm."""
    doc = json.loads((moj.MOJ_RAW_DIR / f"{file_id}.json").read_bytes())["data"]
    attachment = None if moj.has_text_content(doc) else read_attachments.find_attachment(doc)
    lines, articles, origin = read_document_text(doc, attachment)
    checks = {c.name: c for c in check_document(lines, articles, _citation_numbers(articles))} if articles else {}
    return Loaded(doc, lines, articles, origin, checks)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------- các ca (file JSON, lỗi đã gặp, điều phải đúng)


def parts_named_phan(d: Loaded) -> None:
    for number in ("A.VII", "B.I", "B.XII", "C.I", "E.I"):
        expect(number in d.numbers, f"thiếu mục {number}: {d.numbers[:15]}")
    expect(max(len(a.text) for a in d.articles) < 60000, "một mục nuốt cả phần sau (lỗi cũ: 100.146 ký tự)")


def parts_with_skipped_letters(d: Loaded) -> None:
    for number in ("A.VIII", "K.I", "N.I"):
        expect(number in d.numbers, f"thiếu mục {number}: {d.numbers}")


def part_letter_with_dot(d: Loaded) -> None:
    titles = {a.number: a.title for a in d.articles}
    expect(titles.get("A.II") == "MỨC THUẾ MÔN BÀI", f"mục A.II: {titles.get('A.II')!r}")


def source_skips_a_number(d: Loaded) -> None:
    expect("VI" in d.numbers and "VII" in d.numbers, f"bản gốc nhảy IV → VI vẫn phải nhận mục VI, VII: {d.numbers}")


def roman_used_at_two_levels(d: Loaded) -> None:
    expect(not d.checks["thu_tu_de_muc"].passed, "La Mã dùng ở hai cấp → nhãn mục có thể sai → phải cách ly")


def source_repeats_a_number(d: Loaded) -> None:
    expect(not d.checks["thu_tu_de_muc"].passed, "bản gốc có hai mục III → phải cách ly")


def word_conversion_partly_wrong(d: Loaded) -> None:
    expect(d.text_origin == "ocr", f"Word chuyển sai một phần → chỉ để tìm, đang là {d.text_origin}")
    expect(not d.checks["ma_chu"].passed, "còn mã TCVN3 → ma_chu phải trượt")


def portal_html_has_tcvn3(d: Loaded) -> None:
    expect(not d.checks["ma_chu"].passed, "HTML của cổng còn chữ TCVN3 ('Dông cô tay cÇm') → ma_chu phải trượt")


def micro_sign_is_not_tcvn3(d: Loaded) -> None:
    expect("100±5µm" in d.text(), "đơn vị µm bị đổi thành chữ 'à'")


def rtf_tcvn3_converted(d: Loaded) -> None:
    expect("CỦA BỘ TÀI CHÍNH SỐ 360-TC/TCT" in d.text(), "RTF phông TCVN3 chưa ra Unicode")
    expect(d.checks["ma_chu"].passed, d.checks["ma_chu"].detail)


def json_holds_another_document(d: Loaded) -> None:
    header = read_header_number(plain_text(d.doc, 1200))
    expect(header_matches_number(header, d.doc["docNum"]) is False,
           f"JSON của NĐ 125/2020 là công văn 29/CP-KTTH → phải phát hiện lệch (đầu văn bản ghi {header!r})")


def broken_dot_after_article_number(d: Loaded) -> None:
    titles = {a.number: a.title for a in d.articles}
    expect(titles.get("4") == "Hàng hóa GIC", f"'Điều 4ể Hàng hóa GIC' là đề mục thật: {titles.get('4')!r}")


def reference_sentence_is_not_a_heading(d: Loaded) -> None:
    numbers = d.numbers
    expect(numbers == sorted(set(numbers), key=numbers.index) and d.checks["thu_tu_de_muc"].passed,
           f"'Điều 2 dùng để bù trừ…' không được mở Điều mới: {numbers} — {d.checks['thu_tu_de_muc'].detail}")


def word_control_characters(d: Loaded) -> None:
    expect(d.text_origin == "native", f"chữ Word phải là 'native', đang là {d.text_origin}")
    expect(d.checks["ma_chu"].passed, f"ký tự điều khiển của Word không phải chữ hỏng: {d.checks['ma_chu'].detail}")
    expect("Mẫu số: 08/TNDN (Ban hành kèm theo" in d.text(), "dấu xuống dòng trong khung phải thành khoảng trắng")


def word_footnotes_are_not_articles(d: Loaded) -> None:
    expect(not any(n.startswith("QC") for n in d.numbers),
           f"chú thích của Word (\"Điều 7 Thông tư số 119/2014…\", \"“Điều 6. Hiệu lực…\") không được thành Điều: {d.numbers[-4:]}")
    expect(d.checks["thu_tu_de_muc"].passed, d.checks["thu_tu_de_muc"].detail)


def modern_law_is_clean(d: Loaded) -> None:
    titles = {a.number: a.title for a in d.articles}
    expect(titles.get("10") == "Thuế suất", f"Điều 10: {titles.get('10')!r}")
    failed = [c.name for c in d.checks.values() if not c.passed]
    expect(not failed, f"văn bản hiện hành chuẩn không được trượt phép kiểm nào: {failed}")


CASES: list[tuple[str, str, Callable[[Loaded], None]]] = [
    ("13053", "60/2007/TT-BTC — đề mục 'Phần A', mỗi phần đánh mục lại từ I", parts_named_phan),
    ("14086", "59/2007/TT-BTC — phần A…N bỏ chữ (H → K)", parts_with_skipped_letters),
    ("10052", "99/TC-TCT — phần 'A.' trơn viết hoa", part_letter_with_dot),
    ("108427", "53-TC/TCT — bản gốc nhảy số IV → VI", source_skips_a_number),
    ("108107", "07-TC/TCT — số La Mã dùng ở hai cấp", roman_used_at_two_levels),
    ("10484", "29/TC-TCT — bản gốc có hai mục III", source_repeats_a_number),
    ("107401", "221 TC/QĐ/TCT — Word chuyển TCVN3 sai một phần", word_conversion_partly_wrong),
    ("18707", "90/2004/QĐ-BTC — HTML của cổng còn chữ TCVN3", portal_html_has_tcvn3),
    ("107419", "15350/BTC-CST — 'µm' không phải mã TCVN3", micro_sign_is_not_tcvn3),
    ("107460", "360-TC/TCT — RTF phông TCVN3", rtf_tcvn3_converted),
    ("146458", "125/2020/NĐ-CP — JSON chứa văn bản khác", json_holds_another_document),
    ("110920", "201/2015/TT-BTC — dấu chấm sau số Điều hỏng thành chữ ('Điều 4ể')", broken_dot_after_article_number),
    ("f8675990-7e67-11f1-94d4-6bea8b17e7ec", "86/2026/TT-BTC — câu dẫn chiếu đầu dòng 'Điều 2 dùng để…'",
     reference_sentence_is_not_a_heading),
    ("121626", "11/VBHN-BTC (Word từ congbao) — Tika ghi ký tự điều khiển Word (dấu chú thích, xuống dòng) thành '�'",
     word_control_characters),
    ("121632", "13/VBHN-BTC (Word từ congbao) — chú thích Word nằm sau phần thân, trích Điều của văn bản khác",
     word_footnotes_are_not_articles),
    ("a0e29880-8fea-11f1-8351-d98190d5a1c4", "113/VBHN-VPQH — luật hiện hành chuẩn; chú thích cuối '[20] Điều 44 của…'",
     modern_law_is_clean),
]


def run_cases() -> list[tuple[str, str, str | None]]:
    """(file, mô tả, lỗi hoặc None) cho từng ca."""
    results = []
    for file_id, description, case in CASES:
        try:
            case(load(file_id))
            results.append((file_id, description, None))
        except Exception as e:  # thiếu file cũng là ca trượt — bộ đo phải chạy được trọn
            results.append((file_id, description, f"{type(e).__name__}: {e}"))
    return results


def main() -> None:
    results = run_cases()
    for file_id, description, error in results:
        print(f"{'ĐẠT ' if error is None else 'TRƯỢT'}  {description}" + (f"\n        → {error}" if error else ""))
    failed = sum(error is not None for _, _, error in results)
    print(f"{len(results) - failed}/{len(results)} ca đạt")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

"""Chữ của file đính kèm — cho văn bản mà JSON cổng Bộ Tư pháp không có chữ.

Apache Tika (chạy hàng loạt, Tika Pipes) đọc .doc Word 97, RTF, PDF → XHTML ở data/converted/, mỗi file một lần
(docs/architecture.md, Đọc file đính kèm; số đo ở docs/danh-gia.md mục 2). Đọc XHTML bằng bộ tách dòng HTML có sẵn,
bỏ header/footer trang (div class="header|footer"). Tika không chuyển chữ phông TCVN3 ở header RTF và ở một số
đoạn → sửa theo từng dòng (fix_tcvn3_line), đếm trong báo cáo. Mọi chữ từ PDF coi là OCR — chỉ để tìm, không trích.
Đổi cách đọc ở đây → tăng PARSER_VERSION (split_articles) để database nạp lại.

Chạy (trong pipeline: công đoạn converted_attachments):
    python -m app.ingest.read_attachments           Tika đọc file đính kèm chưa có bản XHTML (cần Java + Tika)
    python -m app.ingest.read_attachments --check   bài tự kiểm (không cần Java)
"""

import logging
import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.ingest import download_moj_documents as moj
from app.ingest.download_from_congbao import CONGBAO_RAW_DIR
from app.ingest.split_articles import TextLine, html_to_text_lines
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

WORD_SUFFIXES = {".doc", ".rtf"}
READABLE_SUFFIXES = WORD_SUFFIXES | {".pdf"}
SKIPPED_DIV_CLASSES = ("header", "footer")  # header/footer trang trong XHTML của Tika
TIKA_TIMEOUT_MILLIS = 120_000  # một file quá 2 phút → Tika bỏ, ghi lỗi (mặc định của Tika là 1 giờ)
TIKA_PROCESSES = 2

# ---------------------------------------------------------------- TCVN3 (bảng mã ABC) → Unicode
# Bảng theo Vietnamese Unicode FAQ (vietunicode.sourceforge.net/charset), cột TCVN3. Chữ hoa có dấu
# không có mã riêng — văn bản dùng phông chữ hoa (.VnTimeH) với mã chữ thường, nên dòng sửa ra chữ thường.
TCVN3_CODES = {
    0xA1: "Ă", 0xA2: "Â", 0xA3: "Ê", 0xA4: "Ô", 0xA5: "Ơ", 0xA6: "Ư", 0xA7: "Đ",
    0xA8: "ă", 0xA9: "â", 0xAA: "ê", 0xAB: "ô", 0xAC: "ơ", 0xAD: "ư", 0xAE: "đ",
    0xB5: "à", 0xB6: "ả", 0xB7: "ã", 0xB8: "á", 0xB9: "ạ",
    0xBB: "ằ", 0xBC: "ẳ", 0xBD: "ẵ", 0xBE: "ắ", 0xC6: "ặ",
    0xC7: "ầ", 0xC8: "ẩ", 0xC9: "ẫ", 0xCA: "ấ", 0xCB: "ậ",
    0xCC: "è", 0xCE: "ẻ", 0xCF: "ẽ", 0xD0: "é", 0xD1: "ẹ",
    0xD2: "ề", 0xD3: "ể", 0xD4: "ễ", 0xD5: "ế", 0xD6: "ệ",
    0xD7: "ì", 0xD8: "ỉ", 0xDC: "ĩ", 0xDD: "í", 0xDE: "ị",
    0xDF: "ò", 0xE1: "ỏ", 0xE2: "õ", 0xE3: "ó", 0xE4: "ọ",
    0xE5: "ồ", 0xE6: "ổ", 0xE7: "ỗ", 0xE8: "ố", 0xE9: "ộ",
    0xEA: "ờ", 0xEB: "ở", 0xEC: "ỡ", 0xED: "ớ", 0xEE: "ợ",
    0xEF: "ù", 0xF1: "ủ", 0xF2: "ũ", 0xF3: "ú", 0xF4: "ụ",
    0xF5: "ừ", 0xF6: "ử", 0xF7: "ữ", 0xF8: "ứ", 0xF9: "ự",
    0xFA: "ỳ", 0xFB: "ỷ", 0xFC: "ỹ", 0xFD: "ý", 0xFE: "ỵ",
}
TCVN3_TO_UNICODE = str.maketrans({chr(code): char for code, char in TCVN3_CODES.items()})
# Ký tự chỉ gặp khi chữ là mã TCVN3 đọc nhầm thành Latin-1 ("Bé tµi chÝnh"): mã TCVN3 trừ chữ Việt
# Latin-1 (à, é, ô…) và trừ ký hiệu có thể có thật trong văn bản Unicode (§ ­ « » ® ·, dấu nhân/chia trong
# công thức như "37,702 triệu đồng × 25%").
TCVN3_SIGNATURE = (
    {chr(code) for code in TCVN3_CODES}
    - set("ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúý")
    - set("§­«»®·×÷")
)
MICRO_UNIT = re.compile(r"\dµ")


def has_vietnamese_unicode(text: str) -> bool:
    """Có chữ Việt ngoài Latin-1 (ă, ơ, ư, đ, ộ…) → dòng đã là Unicode."""
    return any("Ă" <= c <= "ỹ" for c in text)


def fix_tcvn3_line(text: str) -> str:
    """Dòng còn mã TCVN3 (có ký tự đặc trưng, không có chữ Việt Unicode) → Unicode. Dòng khác giữ nguyên."""
    # "µ" sau chữ số là đơn vị micro ("100±5µm"), không phải "à" của TCVN3.
    signature_text = MICRO_UNIT.sub("", text)
    if has_vietnamese_unicode(text) or not any(c in TCVN3_SIGNATURE for c in signature_text):
        return text
    return text.translate(TCVN3_TO_UNICODE)


def looks_garbled(lines: list[TextLine]) -> bool:
    """Còn dòng mang mã TCVN3 sau khi sửa (trộn với Unicode trên cùng dòng — bộ sửa không dám đổi)."""
    return any(sum(c in TCVN3_SIGNATURE for c in line.text) >= 2 for line in lines)


def xhtml_to_text_lines(xhtml: str) -> list[TextLine]:
    """XHTML của Tika → các dòng chữ: bỏ header/footer trang, sửa mã TCVN3 còn sót, chuẩn hoá NFC."""
    lines = []
    for line in html_to_text_lines(xhtml, SKIPPED_DIV_CLASSES):
        text = unicodedata.normalize("NFC", fix_tcvn3_line(line.text))
        lines.append(TextLine(text))
    return lines


# ---------------------------------------------------------------- tìm file đính kèm của một văn bản


def converted_path(source: Path) -> Path:
    """data/raw/moj/files/123/a.doc → data/converted/moj/files/123/a.doc.xml (cách Tika Pipes đặt tên)."""
    return config.CONVERTED_DATA_DIR / source.relative_to(config.RAW_DATA_DIR).parent / (source.name + ".xml")


@dataclass
class Attachment:
    source: Path  # bản gốc trên đĩa — băm file này để biết văn bản có đổi không
    readable: Path  # XHTML Tika đọc ra
    text_origin: str  # 'native' (Word/RTF — được trích) | 'ocr' (PDF — chỉ để tìm)


def find_attachment(doc: dict) -> Attachment | None:
    """File đính kèm tốt nhất của văn bản: Word/RTF trước, PDF sau — chỉ file Tika đã đọc xong.

    Tìm trong file của cổng Bộ Tư pháp, rồi bản tải từ congbao (cùng mã văn bản Bộ Tư pháp).
    """
    candidates = [moj.ATTACHMENTS_DIR / doc["id"] / name for name in moj.safe_attachment_names(doc)]
    congbao_dir = CONGBAO_RAW_DIR / doc["id"]
    if congbao_dir.is_dir():
        candidates += sorted(p for p in congbao_dir.iterdir() if p.name != "meta.json")
    candidates = [p for p in candidates if p.is_file() and converted_path(p).exists()]
    for path in candidates:
        if path.suffix.lower() in WORD_SUFFIXES:
            return Attachment(path, converted_path(path), "native")
    for path in candidates:
        if path.suffix.lower() == ".pdf":
            return Attachment(path, converted_path(path), "ocr")
    return None


def read_attachment_lines(attachment: Attachment) -> list[TextLine]:
    lines = xhtml_to_text_lines(attachment.readable.read_text(encoding="utf-8", errors="replace"))
    if attachment.text_origin != "native":
        return lines  # PDF: "�" là glyph không đọc được — giữ lại để phép kiểm ma_chu bắt
    # Word: Tika (Apache POI) ghi chú thích SAU HẾT phần thân, mỗi đoạn chú thích mở đầu bằng dấu tham chiếu "�"
    # (ví dụ các văn bản hợp nhất 10–14/VBHN-BTC). Vùng chú thích trích Điều của văn bản khác
    # ("“Điều 6. Hiệu lực thi hành…") → không thuộc Điều nào, bỏ khỏi chữ đem tách.
    footnotes_start = next((i for i, line in enumerate(lines) if line.text.startswith("�")), len(lines))
    # "�" còn lại giữa dòng là ký tự điều khiển Word (xuống dòng trong khung: "Mẫu số: 08/TNDN�(Ban hành") — không mất chữ.
    return [TextLine(" ".join(line.text.replace("�", " ").split())) for line in lines[:footnotes_start]]


# ---------------------------------------------------------------- Tika đọc file → XHTML


def readable_files() -> list[Path]:
    """Mọi .doc/.rtf/.pdf trong bản gốc (trừ history/ — bản cũ không dùng)."""
    return sorted(p for p in config.RAW_DATA_DIR.rglob("*")
                  if p.suffix.lower() in READABLE_SUFFIXES and p.is_file() and "history" not in p.parts)


def convert_attachments() -> StageReport:
    """Tika đọc file chưa có bản XHTML. Rồi đo trên mọi bản XHTML: dòng phải sửa mã TCVN3."""
    report = StageReport("doc_file_dinh_kem")
    sources = readable_files()
    to_convert = [s for s in sources if not converted_path(s).exists()]
    report.count("da_doc_tu_truoc", len(sources) - len(to_convert))
    log.info("%d file đính kèm, %d cần Tika đọc", len(sources), len(to_convert))
    if to_convert:
        _run_tika(to_convert, report)
    for source in sources:
        target = converted_path(source)
        if not target.exists():
            continue
        raw = [line.text for line in html_to_text_lines(target.read_text(encoding="utf-8", errors="replace"),
                                                          SKIPPED_DIV_CLASSES)]
        fixed = sum(fix_tcvn3_line(t) != t for t in raw)
        report.count("dong_sua_ma_tcvn3", fixed)
        report.count("file_co_dong_sua_ma_tcvn3", fixed > 0)
    return report


def _run_tika(sources: list[Path], report: StageReport) -> None:
    """Tika Pipes: `java -jar tika-app.jar -i <bản gốc> -o <đích> --fileList …` (tika-app 4.1.0 --help)."""
    for path in (config.JAVA_EXE, config.TIKA_APP_JAR):
        if not Path(path).is_file():
            raise RuntimeError(f"Không thấy {path} — đặt JAVA_EXE, TIKA_APP_JAR trong .env (docs/architecture.md)")
    config.CONVERTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as file_list:
        file_list.write("\n".join(s.relative_to(config.RAW_DATA_DIR).as_posix() for s in sources))
    try:
        result = subprocess.run(
            [str(config.JAVA_EXE), "-jar", str(config.TIKA_APP_JAR),
             "-i", str(config.RAW_DATA_DIR), "-o", str(config.CONVERTED_DATA_DIR),
             "--fileList", file_list.name, "--handler", "x", "--content-only", "--on-exists", "replace",
             "-p", str(Path(config.TIKA_APP_JAR).parent / "plugins"),
             "-n", str(TIKA_PROCESSES), "-T", str(TIKA_TIMEOUT_MILLIS)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        Path(file_list.name).unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"Tika dừng với mã {result.returncode}: {result.stderr[-500:]}")
    for source in sources:  # Tika bỏ qua file hỏng, file quá giờ — file nào không có đầu ra là lỗi
        if converted_path(source).exists():
            report.count("doc_moi")
        else:
            report.fail(str(source.relative_to(config.RAW_DATA_DIR)), "Tika không đọc ra (hỏng, có mật khẩu hoặc quá giờ)", log)


# ---------------------------------------------------------------- tự kiểm


def self_check() -> None:
    assert fix_tcvn3_line("Bé tµi chÝnh") == "Bộ tài chính"
    assert fix_tcvn3_line("v¨n phßng quèc héi") == "văn phòng quốc hội"
    assert fix_tcvn3_line("Thuế suất 10%") == "Thuế suất 10%", "dòng Unicode giữ nguyên"
    assert fix_tcvn3_line("Bá cáo năm") == "Bá cáo năm", "có chữ Việt Unicode → không sửa"
    assert fix_tcvn3_line("Hà Tây, ngày 5") == "Hà Tây, ngày 5", "chữ Việt Latin-1 không phải dấu hiệu TCVN3"
    assert fix_tcvn3_line("§ 3 và «trích»") == "§ 3 và «trích»", "ký hiệu thật không bị coi là TCVN3"
    assert fix_tcvn3_line("100±5µm") == "100±5µm", "µ sau chữ số là đơn vị micro"
    assert fix_tcvn3_line("× 2 (quý) × 50%") == "× 2 (quý) × 50%", "dấu nhân trong công thức giữ nguyên"

    xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><head><meta name="dc:title" content="tiêu đề"/>
      <title>x</title></head><body>
      <div class="header"><p>60 CÔNG BÁO/Số 393 + 394</p><div><p>lồng trong header</p></div></div>
      <p>Điều 1. Phạm vi</p><p>dòng một<br/>dòng   hai</p>
      <table><tr><td>ô</td><td>bảng</td></tr></table>
      <p>Bé tµi chÝnh</p>
      <div class="footer"><p>Trang 2</p></div>
      <div class="page"><p>chữ PDF</p></div>
    </body></html>"""
    lines = [line.text for line in xhtml_to_text_lines(xhtml)]
    assert lines == ["Điều 1. Phạm vi", "dòng một", "dòng hai", "ô bảng", "Bộ tài chính", "chữ PDF"], lines

    sample = config.RAW_DATA_DIR / "moj" / "files" / "1" / "a.doc"
    assert converted_path(sample) == config.CONVERTED_DATA_DIR / "moj" / "files" / "1" / "a.doc.xml"
    print("PASS")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(convert_attachments().summary())


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

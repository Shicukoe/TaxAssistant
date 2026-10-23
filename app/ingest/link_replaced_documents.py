"""Đọc câu "… hết hiệu lực kể từ …", "… này thay thế / bãi bỏ …" trong Điều hiệu lực của văn bản mới → quan hệ thay_the / bai_bo (docs/architecture.md, Model AI).

Chạy (sau save_to_database; trong pipeline: công đoạn replaced_links):
    python -m app.ingest.link_replaced_documents
    python -m app.ingest.link_replaced_documents --check     (bài tự kiểm, không cần database)

Cổng Bộ Tư pháp không ghi ngày hết hiệu lực cho Luật Quản lý thuế 38/2019 dù Luật 108/2025 (khoản 3 Điều 52) ghi
"Luật Quản lý thuế số 38/2019/QH14 … hết hiệu lực thi hành kể từ ngày Luật này có hiệu lực thi hành". Ba dạng câu:
  1. "<Loại> … số <số hiệu> … hết hiệu lực [thi hành] [kể từ ngày <Loại> này có hiệu lực | kể từ ngày dd tháng mm năm yyyy]"
  2. "Kể từ ngày <Loại> này có hiệu lực thi hành, <Loại> số <số hiệu> … hết hiệu lực"
  3. "Kể từ ngày …, các Nghị định sau đây hết hiệu lực thi hành:" + các dòng "a) Nghị định số …"
  4. "Nghị định này thay thế: a) Nghị định số 126/2020/NĐ-CP …" (NĐ 252/2026), "Thông tư này bãi bỏ: …" (TT 89/2026),
     hoặc trên một dòng "Nghị định này thay thế Nghị định số 83/2013/NĐ-CP" → bai_bo khi chữ là "bãi bỏ"
Chỉ nhận cả văn bản: mục "b) Điều 1 Nghị định số 41/2022…", "Chương I … Nghị định …" là hết hiệu lực một phần → bỏ.
Văn bản thứ hai trở đi chỉ nhận khi nối ngay sau văn bản trước ("Thông tư số 166/2013/TT-BTC ngày …, Thông tư số
10/2014/TT-BTC …"), không nhận khi nằm sau phần mô tả ("… hướng dẫn Luật …, Nghị định số 123/2020" là văn bản được
nhắc, không phải văn bản bị thay). Bỏ sót an toàn hơn gắn nhầm. Văn bản hợp nhất không đọc: câu trong đó chép lại
từ văn bản gốc. Tính lại toàn bộ mỗi lần chạy.
"""

import logging
import re
import sys
from collections import defaultdict
from datetime import date

import psycopg

from app import config
from app.answer.search_articles import provision_label
from app.ingest.link_consolidated_documents import normalize_number
from app.ingest.stage_report import StageReport

log = logging.getLogger(__name__)

TYPES = r"(?:Bộ luật|Luật|Pháp lệnh|Nghị quyết|Nghị định|Quyết định|Thông tư liên tịch|Thông tư)"
NUMBER = r"\d+[A-Za-zĐđ]*/(?:\d{4}/)?[A-Za-zĐđÐ0-9-]+"  # 38/2019/QH14, 100/2020/NĐ-CP, 954/2020/UBTVQH14
ISSUED = r"(?:\s+ngày\s+(?:\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}))?"
# Tên văn bản có thể chứa dấu phẩy ("Luật thuế xuất khẩu, thuế nhập khẩu số 45/2005/QH11") nhưng không chứa . ; :
SUBJECT = re.compile(rf"(?P<type>{TYPES})\b[^.;:]{{0,150}}?\s(?:(?:số|sổ)\s*)?(?P<number>{NUMBER})")
NEXT_SUBJECT = re.compile(rf"{ISSUED}(?:,\s*|\s+và\s+)(?P<type>{TYPES})\b[^.;:]{{0,150}}?\s(?:(?:số|sổ)\s*)?(?P<number>{NUMBER})")
LEADING = re.compile(rf"\s*(?:\d+\.|[a-zđ]\)|-)?\s*(?:Kể từ ngày {TYPES} này có hiệu lực(?: thi hành)?,\s*)?")
EXPIRES = re.compile(r"\bhết hiệu lực(?: thi hành)?")
SINCE_THIS = re.compile(rf"kể từ ngày {TYPES} này có hiệu lực", re.IGNORECASE)
SINCE_DATE = re.compile(r"từ ngày\s+(?:(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})|(\d{1,2})/(\d{1,2})/(\d{4}))")
# "… sau đây hết hiệu lực thi hành:", "… hết hiệu lực thi hành kể từ ngày …, trừ quy định tại Điều 43 …, cụ thể như sau:"
# (NĐ 126/2020), "Nghị định này thay thế:" — câu dẫn kết thúc bằng ":" và không tự nêu số hiệu văn bản bị thay
LIST_INTRO = re.compile(rf"(?:hết hiệu lực|{TYPES} này (?P<verb>thay thế|bãi bỏ))[^:]{{0,150}}:\s*$")
THIS_REPLACES = re.compile(rf"{TYPES} này (?P<verb>thay thế|bãi bỏ)\s+")
LIST_ITEM = re.compile(r"\s*(?:[a-zđ]\)|-)\s*")
SENTENCE_BREAK = re.compile(r";\s+|\.\s+(?=[A-ZĐ])")
MARKER_ONLY = re.compile(r"\s*\d+\.")
EXCEPTION = re.compile(r"\btrừ\b")

SOURCE_SQL = """
    select d.id::text, d.so_hieu, d.loai, d.eff_from, ch.id, ch.text, p.level, p.so
    from chunks ch
    join documents d on d.id = ch.document_id
    join provisions p on p.id = ch.dieu_provision_id
    where d.doc_group <> 'VBHN' and d.text_origin = 'native' and ch.text ~ 'hết hiệu lực|này thay thế|này bãi bỏ'
      and lower(f_unaccent(coalesce(p.ten, ''))) ~ 'hieu luc|thi hanh|chuyen tiep'"""


def subject_numbers(text: str) -> list[str]:
    """Số hiệu các văn bản bị thay, khi `text` mở đầu bằng tên văn bản; [] nếu không."""
    match = SUBJECT.match(text)
    if not match:
        return []
    numbers = [match["number"]]
    while follow := NEXT_SUBJECT.match(text, match.end()):
        numbers.append(follow["number"])
        match = follow
    return numbers


def replacement_date(text: str, own_effective_from: date | None) -> date | None:
    """Ngày văn bản cũ hết hiệu lực: ghi rõ trong `text`, hoặc ngày văn bản mới có hiệu lực. `text` chỉ gồm phần nói về
    thời điểm (đoạn mở đầu "Kể từ ngày …" và phần sau chữ "hết hiệu lực") — phần mô tả văn bản bị thay có thể chứa
    "có hiệu lực từ ngày 30 tháng 12 năm 2022" của chính nó (NĐ 206/2025 bãi bỏ NĐ 127/2022)."""
    if SINCE_THIS.search(text):
        return own_effective_from
    if match := SINCE_DATE.search(text):
        day, month, year = (int(x) for x in (match.groups()[:3] if match[1] else match.groups()[3:]))
        return date(year, month, day)
    return own_effective_from


def relation_kind(verb: str | None) -> str:
    return "bai_bo" if verb == "bãi bỏ" else "thay_the"


def read_statements(text: str, own_effective_from: date | None) -> list[dict]:
    """Câu tuyên bố trong một Điều: số hiệu bị thay, loại quan hệ, ngày, vị trí ký tự (để lấy số khoản), nguyên văn,
    có "trừ" không."""
    found = []
    lines, offset = [], 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1
    index = 0
    while index < len(lines):
        start, line = lines[index]
        index += 1
        if (intro := LIST_INTRO.search(line)) and not SUBJECT.match(line[LEADING.match(line).end():]):
            # dạng 3, 4: các dòng sau là danh sách văn bản; "trừ …" ở câu dẫn áp cho cả danh sách
            since, kind = replacement_date(line, own_effective_from), relation_kind(intro["verb"])
            intro_exceptions = bool(EXCEPTION.search(line))
            while index < len(lines) and (marker := LIST_ITEM.match(lines[index][1])):
                item_start, item = lines[index]
                index += 1
                for number in subject_numbers(item[marker.end():]):
                    found.append({"number": number, "kind": kind, "date": since, "position": item_start,
                                  "quote": item.strip(),
                                  "has_exceptions": intro_exceptions or bool(EXCEPTION.search(item))})
            continue
        # "3. Luật …": dấu chấm sau số khoản không phải hết câu
        breaks = [m.end() for m in SENTENCE_BREAK.finditer(line) if not MARKER_ONLY.fullmatch(line[:m.start() + 1])]
        pieces = [0] + breaks + [len(line)]
        for begin, end in zip(pieces, pieces[1:]):
            sentence = line[begin:end]
            body = sentence[LEADING.match(sentence).end():]
            if replaces := THIS_REPLACES.match(body):  # dạng 4 trên một dòng
                for number in subject_numbers(body[replaces.end():]):
                    found.append({"number": number, "kind": relation_kind(replaces["verb"]),
                                  "date": own_effective_from, "position": start + begin,
                                  "quote": sentence.strip(), "has_exceptions": bool(EXCEPTION.search(body))})
                continue
            expires = EXPIRES.search(body)
            numbers = subject_numbers(body)
            if not expires or not numbers or SUBJECT.match(body).start("number") > expires.start():
                continue
            for number in numbers:
                timing = sentence[:len(sentence) - len(body)] + body[expires.end():]
                found.append({"number": number, "kind": "thay_the", "date": replacement_date(timing, own_effective_from),
                              "position": start + begin, "quote": sentence.strip(),
                              "has_exceptions": bool(EXCEPTION.search(body[expires.end():]))})
    return found


def link_replaced_documents() -> StageReport:
    report = StageReport("replaced_links")
    with psycopg.connect(config.DATABASE_CONNECTION) as conn:
        by_number = defaultdict(list)
        for document_id, so_hieu in conn.execute("select id::text, so_hieu from documents where doc_group <> 'VBHN'"):
            by_number[normalize_number(so_hieu)].append(document_id)
        relations = []
        for document_id, so_hieu, loai, effective_from, chunk_id, text, level, number in conn.execute(SOURCE_SQL).fetchall():
            try:
                for statement in read_statements(text, effective_from):
                    target = normalize_number(statement["number"])
                    if target == normalize_number(so_hieu):
                        continue
                    if statement["date"] is None:
                        report.count("khong_ro_ngay")
                        continue
                    candidates = by_number.get(target, [])
                    if len(candidates) > 1:
                        report.count("so_hieu_trung_khong_phan_biet_duoc")
                        continue
                    clause = conn.execute(
                        "select so from chunk_positions where chunk_id = %s and level = 'khoan' "
                        "and char_start <= %s and %s < char_end order by char_end - char_start limit 1",
                        (chunk_id, statement["position"], statement["position"])).fetchone()
                    label = provision_label(level, number)
                    label = f"khoản {clause[0]} {label}" if clause else label
                    report.count(f"quan_he_{statement['kind']}" if candidates else "van_ban_bi_thay_chua_co_trong_kho")
                    relations.append((document_id, candidates[0] if candidates else None, statement["number"],
                                      statement["kind"],
                                      statement["date"], label, statement["quote"][:1000], statement["has_exceptions"]))
            except Exception as e:  # một văn bản lỗi không chặn văn bản khác (quy tắc bất biến số 11)
                report.fail(so_hieu, e, log)
        with conn.transaction():
            conn.execute("delete from document_relations where relation_type in ('thay_the', 'bai_bo')")
            conn.cursor().executemany(
                "insert into document_relations (from_doc, to_doc, to_doc_ref, relation_type, evidence, confidence, "
                "effective_from, source_label, quote, has_exceptions) "
                "values (%s, %s, %s, %s, 'text_parse', 1.0, %s, %s, %s, %s)", relations)
    log.info(report.summary())
    return report


def self_check() -> None:
    effect = date(2026, 7, 1)
    text = ("Điều 52. Điều khoản thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
            "3. Luật Quản lý thuế số 38/2019/QH14 đã được sửa đổi, bổ sung một số điều theo Luật số 56/2024/QH15 hết "
            "hiệu lực thi hành kể từ ngày Luật này có hiệu lực thi hành, trừ quy định tại khoản 1 Điều 53 của Luật này; "
            "riêng quy định tại Điều 51 của Luật Quản lý thuế số 38/2019/QH14 hết hiệu lực thi hành kể từ ngày 01 tháng "
            "01 năm 2026.")
    [statement] = read_statements(text, effect)
    assert (statement["number"], statement["date"], statement["has_exceptions"]) == ("38/2019/QH14", effect, True)
    assert text[statement["position"]:].startswith("3. Luật Quản lý thuế"), statement
    text = ("2. Kể từ ngày Nghị định này có hiệu lực thi hành, các Nghị định sau đây hết hiệu lực thi hành:\n"
            "a) Nghị định số 123/2020/NĐ-CP ngày 19 tháng 10 năm 2020 của Chính phủ quy định về hóa đơn, chứng từ;\n"
            "b) Điều 1 Nghị định số 41/2022/NĐ-CP ngày 20 tháng 6 năm 2022 sửa đổi Nghị định số 123/2020/NĐ-CP;\n"
            "c) Nghị định số 70/2025/NĐ-CP ngày 20 tháng 3 năm 2025 sửa đổi, bổ sung Nghị định số 123/2020/NĐ-CP.\n"
            "d) Thông tư số 166/2013/TT-BTC ngày 15 tháng 11 năm 2013, Thông tư số 10/2014/TT-BTC ngày 17 tháng 01 "
            "năm 2014 và Thông tư số 176/2016/TT-BTC ngày 31 tháng 10 năm 2016 của Bộ Tài chính.\n3. Khoản khác.")
    numbers = [s["number"] for s in read_statements(text, effect)]
    assert numbers == ["123/2020/NĐ-CP", "70/2025/NĐ-CP", "166/2013/TT-BTC", "10/2014/TT-BTC", "176/2016/TT-BTC"], numbers
    text = ("Kể từ ngày Thông tư này có hiệu lực thi hành, Thông tư số 32/2025/TT-BTC ngày 31 tháng 5 năm 2025 của Bộ "
            "trưởng Bộ Tài chính hướng dẫn thực hiện một số điều của Luật Quản lý thuế, Nghị định số 123/2020/NĐ-CP "
            "hết hiệu lực thi hành.")
    assert [s["number"] for s in read_statements(text, effect)] == ["32/2025/TT-BTC"], "văn bản được nhắc không bị thay"
    text = "Luật thuế xuất khẩu, thuế nhập khẩu số 45/2005/QH11 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành."
    assert [s["number"] for s in read_statements(text, effect)] == ["45/2005/QH11"]
    text = "Thông tư số 110/2015/TT-BTC ngày 28/7/2015 và Thông tư số 66/2019/TT-BTC ngày 20/9/2019 hết hiệu lực thi hành."
    assert [s["number"] for s in read_statements(text, effect)] == ["110/2015/TT-BTC", "66/2019/TT-BTC"]
    for text in ("Khi quyết định cưỡng chế đã hết hiệu lực mà Kho bạc chưa trích đủ tiền thuế",
                 "Nghị định này hết hiệu lực kể từ ngày 01 tháng 3 năm 2027 trừ các trường hợp sau:",
                 "Việc Nghị quyết này hết hiệu lực không làm phát sinh nghĩa vụ thực hiện lại các công việc"):
        assert read_statements(text, effect) == [], text
    [statement] = read_statements("Nghị định số 51/2010/NĐ-CP hết hiệu lực kể từ ngày 01 tháng 01 năm 2026.", effect)
    assert statement["date"] == date(2026, 1, 1)
    text = ("3. Nghị định này thay thế:\na) Nghị định số 126/2020/NĐ-CP ngày 19 tháng 10 năm 2020 của Chính phủ quy định "
            "chi tiết một số điều của Luật Quản lý thuế;\nb) Nghị định số 91/2022/NĐ-CP ngày 30 tháng 10 năm 2022 sửa đổi "
            "Nghị định số 126/2020/NĐ-CP;\n4. Nghị định số 125/2020/NĐ-CP tiếp tục có hiệu lực thi hành.")
    found = read_statements(text, effect)
    assert [(s["number"], s["kind"]) for s in found] == [("126/2020/NĐ-CP", "thay_the"), ("91/2022/NĐ-CP", "thay_the")], found
    text = ("2. Quy định tại các Nghị định sau đây hết hiệu lực thi hành kể từ ngày Nghị định này có hiệu lực, trừ quy "
            "định tại Điều 43 Nghị định này, cụ thể như sau:\na) Nghị định số 83/2013/NĐ-CP ngày 22 thấng 7 năm 2013 của "
            "Chính phủ quy định chi tiết thi hành Luật Quản lý thuế:\nb) Điều 4 Nghị định số 91/2014/NĐ-CP ngày 01 tháng 10 "
            "năm 2014;")
    [statement] = read_statements(text, effect)
    assert (statement["number"], statement["date"], statement["has_exceptions"]) == ("83/2013/NĐ-CP", effect, True)
    text = "3. Thông tư này bãi bỏ:\na) Thông tư số 179/2013/TT-BTC ngày 02 tháng 12 năm 2013 của Bộ trưởng;"
    assert [(s["number"], s["kind"]) for s in read_statements(text, effect)] == [("179/2013/TT-BTC", "bai_bo")]
    [statement] = read_statements("3. Nghị định này bãi bỏ Nghị định số 127/2022/NĐ-CP ngày 30 tháng 12 năm 2022 về Biểu "
                                  "thuế thực hiện Hiệp định có hiệu lực từ ngày 30 tháng 12 năm 2022.", effect)
    assert statement["date"] == effect, "ngày trong phần mô tả văn bản bị thay"
    [statement] = read_statements("Nghị định số 24/2007/NĐ-CP ngày 14/02/2007 có hiệu lực từ ngày 01/3/2007 hết hiệu lực "
                                  "kể từ ngày 01 tháng 01 năm 2009.", effect)
    assert statement["date"] == date(2009, 1, 1), statement
    [statement] = read_statements("2. Nghị định này thay thế Nghị định số 83/2013/NĐ-CP ngày 22 tháng 7 năm 2013.", effect)
    assert (statement["number"], statement["kind"], statement["date"]) == ("83/2013/NĐ-CP", "thay_the", effect)
    print("PASS")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(link_replaced_documents().summary())


if __name__ == "__main__":
    self_check() if "--check" in sys.argv else main()

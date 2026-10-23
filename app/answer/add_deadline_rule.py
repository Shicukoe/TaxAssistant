"""Thời hạn rơi vào ngày nghỉ (docs/architecture.md, Model AI — Thời hạn rơi vào ngày nghỉ).

Văn bản ghi "chậm nhất là ngày 31 tháng 10"; năm 2026 ngày đó là thứ Bảy, nên theo quy tắc ngày nghỉ (Điều 3 Nghị định
252/2026/NĐ-CP) hạn là thứ Hai 02/11/2026. Model 4B không tự tính thứ trong tuần → code tính (quy tắc bất biến số 12):
  - add_deadline_rule (node, trước khi viết): câu hỏi về thời hạn → thêm Điều quy tắc ngày nghỉ còn hiệu lực tại mốc vào
    ngữ cảnh, tính sẵn lịch cho ngày "D tháng M" trong các đoạn tìm được (và ngày trong câu hỏi) ở năm của mốc;
  - with_calendar_notes (gọi trong check_citations): kết luận nhắc một ngày nghỉ mà chưa nêu ngày lùi → thêm dòng lịch.
Chỉ tính thứ Bảy, Chủ nhật và ngày lễ dương lịch cố định; Tết âm lịch, Giỗ Tổ, ngày nghỉ bù chưa tính.

Chạy bài tự kiểm: python -m app.answer.add_deadline_rule --check
"""

import re
import sys
from datetime import date, timedelta

import psycopg
from psycopg.rows import dict_row

from app import config
from app.answer.search_articles import FILTER_SQL, FROM_SQL, SELECT_COLUMNS, load_chunk_texts
from app.answer.understand_question import remove_diacritics

# Câu hỏi về thời hạn (đã bỏ dấu): "thời hạn", "hạn cuối", "hạn nộp", "là hạn", "chậm nhất", "đến hạn", "quá hạn"
# "gia hạn nộp" không phải câu hỏi về ngày cuối cùng của thời hạn
DEADLINE_WORDS = re.compile(
    r"\b(?:thoi han|(?<!gia )han (?:cuoi|chot|nop|khai)|la han|cham nhat|den han|qua han|ngay cuoi)\b")
# Ngày lễ dương lịch cố định (Bộ luật Lao động 2019, Điều 112): Tết Dương lịch, 30/4, 1/5, Quốc khánh 2/9
FIXED_HOLIDAYS = {(1, 1), (30, 4), (1, 5), (2, 9)}
WEEKDAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]
LONG_DATE = re.compile(r"ngày (\d{1,2}) tháng (\d{1,2})(?!\d)(?: năm (\d{4}))?")
SHORT_DATE = re.compile(r"(?<![\d/])(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?(?![\d/])")  # "2-11", "31/10", "02/11/2026"
# Ngày ghi đủ năm trong kết luận, kèm thứ nếu có: "31/10/2026 là thứ Bảy", "ngày 31 tháng 10 năm 2026 (Chủ nhật)"
DATED = re.compile(
    r"(?:(?<![\d/])(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})"
    r"|ngày (?P<day2>\d{1,2}) tháng (?P<month2>\d{1,2}) năm (?P<year2>\d{4}))"
    r"(?:\s*(?:là|,|\()?\s*(?P<weekday>thứ (?:Hai|Ba|Tư|Năm|Sáu|Bảy)|Chủ nhật))?", re.IGNORECASE)
MAX_NOTES = 5
HOLIDAY_RULE_SQL = f"""
    select {SELECT_COLUMNS}
    {FROM_SQL}
    where {FILTER_SQL}
      and ch.text like '%%ngày cuối cùng của thời hạn%%trùng với ngày nghỉ%%'
    order by d.ngay_ban_hanh desc nulls last
    limit 1"""


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and (day.day, day.month) not in FIXED_HOLIDAYS


def next_working_day(day: date) -> date:
    day += timedelta(days=1)
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def find_dates(text: str, year: int, patterns: tuple[re.Pattern, ...], yearless_only: bool = False) -> list[date]:
    """Ngày trong chữ; không ghi năm thì lấy `year`. yearless_only: bỏ ngày có ghi năm (trong văn bản luật đó là mốc
    lịch sử, không phải thời hạn lặp lại hằng năm)."""
    found = []
    for pattern in patterns:
        for day, month, written_year in pattern.findall(text):
            if yearless_only and written_year:
                continue
            try:
                found.append(date(int(written_year or year), int(month), int(day)))
            except ValueError:  # "31/2", "1/13" — không phải ngày
                continue
    return found


def calendar_note(day: date) -> dict | None:
    """Ghi chú lịch cho ngày nghỉ, hoặc None nếu là ngày làm việc."""
    if is_working_day(day):
        return None
    shifted = next_working_day(day)
    holiday = " (ngày lễ)" if (day.day, day.month) in FIXED_HOLIDAYS else ""
    return {"ngay": day.isoformat(), "ngay_lui": shifted.isoformat(),
            "ghi_chu": f"{day:%d/%m/%Y} là {WEEKDAYS[day.weekday()]}{holiday} → ngày cuối cùng của thời hạn tính là "
                       f"{WEEKDAYS[shifted.weekday()]} {shifted:%d/%m/%Y}"}


def calendar_notes(question: str, passages: list[str], year: int) -> list[dict]:
    """Ngày nghỉ trong câu hỏi (cả dạng "2-11") và trong các đoạn luật (chỉ dạng "ngày D tháng M" không ghi năm).
    Câu hỏi nêu ngày → chỉ giữ ghi chú có ngày đó (là ngày nghỉ, hoặc là ngày lùi tới): ghi chú thừa làm model 4B lấy
    nhầm thứ của ngày khác."""
    asked = find_dates(question, year, (LONG_DATE, SHORT_DATE))
    days = list(asked)
    for text in passages:
        days += find_dates(text, year, (LONG_DATE,), yearless_only=True)
    notes = [note for day in dict.fromkeys(days) if (note := calendar_note(day))]
    asked_iso = {day.isoformat() for day in asked}
    related = [note for note in notes if note["ngay"] in asked_iso or note["ngay_lui"] in asked_iso]
    return (related or notes)[:MAX_NOTES]


def dates_without_basis(conclusion: str, sources: list[str], notes: list[dict], year: int) -> list[str]:
    """Ngày ghi đủ năm trong kết luận mà không có trong nguồn (đoạn trích, câu hỏi) hay lịch đã tính, và câu "ngày X là
    thứ Y" sai thứ. Kiểm cả ngày — kiểm từng số rời thì "01/11/2026" lọt vì "01", "11" có ở chỗ khác."""
    allowed = {day for text in sources for day in find_dates(text, year, (LONG_DATE, SHORT_DATE))}
    allowed |= {date.fromisoformat(note[key]) for note in notes for key in ("ngay", "ngay_lui")}
    problems = []
    for match in DATED.finditer(conclusion):
        day = dated_value(match)
        if day is None or day not in allowed:
            problems.append(match[0])
        elif match["weekday"] and match["weekday"].lower() != WEEKDAYS[day.weekday()].lower():
            problems.append(f"{match[0]} (đúng là {WEEKDAYS[day.weekday()]})")
    return problems


def dated_value(match: re.Match) -> date | None:
    parts = (match["year"] or match["year2"], match["month"] or match["month2"], match["day"] or match["day2"])
    try:
        return date(*map(int, parts))
    except ValueError:
        return None


async def add_deadline_rule(state: dict) -> dict:
    """Node LangGraph. Câu hỏi không nói về thời hạn → không làm gì."""
    if not DEADLINE_WORDS.search(remove_diacritics(state["question"])):
        return {"calendar_notes": []}
    articles = state.get("articles") or []
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        rule = await (await conn.execute(HOLIDAY_RULE_SQL, {"as_of": state["as_of_date"]})).fetchone()
    if rule is not None and rule["chunk_id"] not in {a["chunk_id"] for a in articles}:
        articles = articles + [{**rule, "score": 0.0, "nguon": ["quy_tac_ngay_nghi"]}]
    texts = await load_chunk_texts([a["chunk_id"] for a in articles])
    year = date.fromisoformat(str(state["as_of_date"])[:10]).year
    return {"articles": articles, "calendar_notes": calendar_notes(state["question"], list(texts.values()), year)}


def with_calendar_notes(conclusion: str, question: str, notes: list[dict], year: int) -> str:
    """Kết luận nhắc một ngày nghỉ, hoặc câu hỏi nêu ngày nghỉ / ngày lùi tới → thêm dòng lịch do code tính ở cuối,
    kể cả khi model đã tự viết ngày lùi: dòng này là bản tính tất định để người đọc đối chiếu."""
    in_conclusion = set(find_dates(conclusion, year, (LONG_DATE, SHORT_DATE)))
    in_question = set(find_dates(question, year, (LONG_DATE, SHORT_DATE)))
    lines = [note["ghi_chu"] for note in notes
             if date.fromisoformat(note["ngay"]) in in_conclusion | in_question
             or date.fromisoformat(note["ngay_lui"]) in in_question]
    return conclusion + "".join(f"\n\nLịch: {line}." for line in lines)


def self_check() -> None:
    assert not is_working_day(date(2026, 10, 31)) and next_working_day(date(2026, 10, 31)) == date(2026, 11, 2)
    assert next_working_day(date(2026, 4, 30)) == date(2026, 5, 4), "30/4 thứ Năm, 1/5 thứ Sáu → thứ Hai 4/5"
    assert find_dates("Ngày 2-11 là hạn cuối", 2026, (LONG_DATE, SHORT_DATE)) == [date(2026, 11, 2)]
    assert find_dates("theo 25/2026/VBHN-BTC, giảm 1/13", 2026, (SHORT_DATE,)) == []
    passage = "chậm nhất là ngày 31 tháng 10; có hiệu lực từ ngày 01 tháng 7 năm 2026; ngày 31 tháng 3 năm dương lịch"
    assert find_dates(passage, 2026, (LONG_DATE,), yearless_only=True) == [date(2026, 10, 31), date(2026, 3, 31)]
    notes = calendar_notes("Ngày 2-11 là hạn cuối nộp thuế sử dụng đất phi nông nghiệp", [passage], 2026)
    assert [n["ngay"] for n in notes] == ["2026-10-31"], notes  # 2/11 là thứ Hai, 31/3/2026 là thứ Ba
    assert "thứ Bảy" in notes[0]["ghi_chu"] and "02/11/2026" in notes[0]["ghi_chu"]
    assert DEADLINE_WORDS.search(remove_diacritics("Ngày 2-11 là hạn cuối nộp thuế"))
    assert DEADLINE_WORDS.search(remove_diacritics("Thời hạn nộp tờ khai quý"))
    assert not DEADLINE_WORDS.search(remove_diacritics("Thuế suất thuế thu nhập doanh nghiệp là bao nhiêu?"))
    assert not DEADLINE_WORDS.search(remove_diacritics("năm 2026 có được gia hạn nộp thuế GTGT, TNCN, TNDN"))
    added = with_calendar_notes("Hạn nộp chậm nhất là ngày 31 tháng 10.", "Hạn nộp thuế đất?", notes, 2026)
    assert added.endswith("tính là thứ Hai 02/11/2026."), added
    assert with_calendar_notes("Thuế suất 20%.", "Thuế suất?", notes, 2026) == "Thuế suất 20%."
    assert with_calendar_notes("Đúng.", "Ngày 2-11 là hạn cuối?", notes, 2026).endswith("02/11/2026."), "ngày lùi trong câu hỏi"
    noisy = calendar_notes("Hạn nộp thuế đất phi nông nghiệp?", [passage + "; chậm nhất là ngày 31 tháng 5"], 2026)
    assert [n["ngay"] for n in noisy] == ["2026-10-31", "2026-05-31"], "không nêu ngày → giữ mọi ngày nghỉ"
    wrong = ("Ngày 31/10/2026 là Chủ nhật nên hạn là thứ Hai 01/11/2026. "
             "Hạn chậm nhất ngày 31 tháng 10 năm 2026 (thứ Bảy), lùi sang 02/11/2026 là thứ Hai.")
    problems = dates_without_basis(wrong, [passage], notes, 2026)
    assert problems == ["31/10/2026 là Chủ nhật (đúng là thứ Bảy)", "01/11/2026"], problems
    print("PASS")


if __name__ == "__main__":
    if "--check" in sys.argv:
        self_check()

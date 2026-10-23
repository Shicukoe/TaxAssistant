"""Hiểu câu hỏi: mốc thời gian (quy tắc), loại thuế và loại câu hỏi (quy tắc từ khoá, model chỉ khi quy tắc không ra).

Quy tắc bất biến số 12: thông tin quyết định đúng sai lấy tất định khi làm được. Model (Qwen, T=0) ổn định nhưng
sai có hệ thống (nghiêng về TNCN/TNDN) → chỉ dùng khi không từ khoá nào khớp.
"""

import re
import unicodedata
from datetime import date

from app import config
from app.answer.call_local_model import ask_local_model_for_json

TAX_TYPES = ["GTGT", "TNDN", "TNCN", "ho_kinh_doanh", "hoa_don", "quan_ly_thue_xu_phat", "xuat_nhap_khau", "khac"]
QUESTION_KINDS = ["tra_cuu", "vi_pham", "so_sanh_thoi_gian", "ngoai_pham_vi"]
# Hai loại nhận bằng quy tắc, rẽ nhánh riêng trong answer_graph (docs/architecture.md, Model AI) — model không gán.
SMALL_TALK, CONCEPT = "chao_hoi", "khai_niem"

# Từ khoá viết không dấu, khớp trên câu hỏi đã bỏ dấu.
TAX_TYPE_KEYWORDS = {
    "ho_kinh_doanh": ["ho kinh doanh", "ca nhan kinh doanh", "hkd"],
    "hoa_don": ["hoa don"],
    "quan_ly_thue_xu_phat": ["xu phat", "bi phat", "phat ", "cham nop", "nop cham", "khai cham", "tien cham", "vi pham"],
    "GTGT": ["gtgt", "gia tri gia tang", "vat"],
    "TNDN": ["tndn", "thu nhap doanh nghiep"],
    "TNCN": ["tncn", "thu nhap ca nhan"],
    "xuat_nhap_khau": ["xuat khau", "nhap khau", "hai quan", "mien thue hang"],
}
VIOLATION_KEYWORDS = ["xu phat", "bi phat", "phat ", "vi pham", "cham nop", "nop cham", "khai cham"]
COMPARISON_KEYWORDS = ["so sanh", "khac nhau", "truoc va sau", "thay doi"]

# Câu chào / không phải câu hỏi (đã bỏ dấu): "xin chào", "hello", "cảm ơn", "ok".
SMALL_TALK_PATTERN = re.compile(
    r"^(?:(?:xin )?chao(?: ban| em| anh| chi| co| bot| tro ly)?|hi|hello|hey|alo|hel+o+l*|test|thu|cam on(?: ban| nhe)?"
    r"|thanks?|thank you|ok|oke|okay|vang|da)[\s.!?,]*$"
)
# Câu hỏi khái niệm (đã bỏ dấu): "thuế là gì", "khái niệm hóa đơn", "thế nào là hộ kinh doanh".
CONCEPT_PATTERNS = [
    re.compile(r"^(?:cho (?:toi|minh|em) hoi )?(?:khai niem|dinh nghia)(?: ve| cua)? (?P<term>.+?)[\s.!?]*$"),
    re.compile(r"^(?:cho (?:toi|minh|em) hoi )?the nao (?:la|duoc goi la) (?P<term>.+?)[\s.!?]*$"),
    re.compile(r"^(?:cho (?:toi|minh|em) hoi )?(?P<term>.+?) (?:la gi|la cai gi|nghia la gi|co nghia la gi"
               r"|duoc hieu (?:la gi|nhu the nao)|duoc dinh nghia (?:la gi|nhu the nao))[\s.!?]*$"),
]
MAX_CONCEPT_WORDS = 8  # dài hơn thì là câu hỏi tình huống, không phải hỏi khái niệm


def detect_simple_question(question: str) -> tuple[str | None, str | None]:
    """(loại, thuật ngữ đã bỏ dấu): chào hỏi → (SMALL_TALK, None); khái niệm → (CONCEPT, 'thue'); khác → (None, None)."""
    plain = " ".join(remove_diacritics(question).split())
    if not re.search(r"[a-z]", plain) or SMALL_TALK_PATTERN.match(plain):
        return SMALL_TALK, None
    for pattern in CONCEPT_PATTERNS:
        if (m := pattern.match(plain)) and len(m["term"].split()) <= MAX_CONCEPT_WORDS:
            term = " ".join(re.sub(r"[^a-z0-9 ]", " ", m["term"]).split())
            if term:
                return CONCEPT, term
    return None, None


CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "loai_thue": {"type": "array", "items": {"enum": TAX_TYPES}, "maxItems": 3},
        "loai_cau_hoi": {"enum": QUESTION_KINDS},
    },
    "required": ["loai_thue", "loai_cau_hoi"],
    "additionalProperties": False,
}
CLASSIFY_PROMPT = (
    "Phân loại câu hỏi về thuế Việt Nam. Chỉ trả JSON theo schema.\n"
    "loai_thue: GTGT = thuế giá trị gia tăng; TNDN = thuế thu nhập doanh nghiệp; TNCN = thuế thu nhập cá nhân; "
    "ho_kinh_doanh = hộ, cá nhân kinh doanh; hoa_don = hoá đơn, chứng từ; quan_ly_thue_xu_phat = kê khai, nộp thuế, "
    "xử phạt; xuat_nhap_khau = thuế xuất khẩu, nhập khẩu; khac = loại khác. Chỉ chọn loại câu hỏi thật sự nhắc tới.\n"
    "loai_cau_hoi: tra_cuu = hỏi quy định; vi_pham = hỏi bị phạt, xử lý vi phạm; so_sanh_thoi_gian = so quy định "
    "giữa các thời điểm; ngoai_pham_vi = không phải câu hỏi về thuế."
)


def remove_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để khớp từ khoá ('Hóa đơn' → 'hoa don'). 'đ' không phải dấu kết hợp nên đổi riêng."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def find_as_of_date(question: str, today: date) -> tuple[date | None, str]:
    """Mốc thời gian theo quy tắc. Trả (ngày, nguồn); không đọc được → (None, '').

    'năm 2025' / '2025' → 31/12/2025 (cách quy đổi năm → ngày: chưa chốt). Có nhiều mốc → lấy mốc sau cùng
    (bản demo chưa so sánh nhiều mốc).
    """
    plain = remove_diacritics(question)
    full_dates = re.findall(r"\b(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\b", plain)
    if full_dates:
        day, month, year = full_dates[-1]
        return date(int(year), int(month), int(day)), "ngay_trong_cau_hoi"
    years = re.findall(r"\b((?:19|20)\d{2})\b", plain)
    if years:
        return date(int(years[-1]), 12, 31), "nam_trong_cau_hoi"
    if re.search(r"hien nay|hien hanh|bay gio|hien tai", plain):
        return today, "hien_hanh"
    return None, ""


def match_keywords(question: str) -> tuple[list[str], str | None]:
    """Loại thuế và loại câu hỏi bằng từ khoá. Trả ([], None) nếu không khớp gì."""
    plain = remove_diacritics(question) + " "
    tax_types = [label for label, words in TAX_TYPE_KEYWORDS.items() if any(w in plain for w in words)]
    if any(w in plain for w in VIOLATION_KEYWORDS):
        kind = "vi_pham"
    elif any(w in plain for w in COMPARISON_KEYWORDS) or len(set(re.findall(r"\b(?:19|20)\d{2}\b", plain))) >= 2:
        kind = "so_sanh_thoi_gian"
    else:
        kind = None
    return tax_types, kind


async def understand_question(state: dict) -> dict:
    """Node LangGraph. Hỏi nối tiếp (không từ khoá loại thuế, đã có lượt trước) → mang ô từ lượt trước sang."""
    question = state["question"]
    today = date.today()
    previous_tax_types = state.get("tax_types") or []
    previous_question = state.get("search_text") or ""

    as_of, as_of_source = find_as_of_date(question, today)
    simple_kind, concept_term = detect_simple_question(question)
    if simple_kind:  # chào hỏi / khái niệm: không mang ô từ lượt trước, không gọi model
        return {
            "as_of_date": (as_of or today).isoformat(),
            "as_of_source": as_of_source if as_of else "mac_dinh_hom_nay",
            "tax_types": [], "question_kind": simple_kind, "concept_term": concept_term,
            "label_source": "quy_tac", "search_text": question, "understand_usage": [],
            # đặt lại mỗi lượt: khái niệm không thấy định nghĩa → tìm thường, không qua split_question
            "search_parts": [question], "split_usage": [],
        }
    tax_types, kind = match_keywords(question)
    usage = []

    is_follow_up = not tax_types and bool(previous_tax_types)
    if is_follow_up:
        tax_types, label_source = previous_tax_types, "luot_truoc"
        kind = kind or state.get("question_kind") or "tra_cuu"
        if as_of is None and state.get("as_of_date"):
            as_of, as_of_source = date.fromisoformat(state["as_of_date"]), "luot_truoc"
        search_text = f"{previous_question} {question}"
    else:
        label_source = "tu_khoa"
        search_text = question
        if not tax_types or kind is None:
            labels, call_usage = await ask_local_model_for_json(
                [{"role": "system", "content": CLASSIFY_PROMPT}, {"role": "user", "content": question}],
                CLASSIFY_SCHEMA, temperature=config.LLM_CLASSIFY_TEMPERATURE, max_tokens=200,
            )
            usage.append({**call_usage, "step": "understand_question"})
            if not tax_types:
                tax_types = list(dict.fromkeys(labels["loai_thue"]))  # model đôi khi trả nhãn trùng
                label_source = "model"
            kind = kind or labels["loai_cau_hoi"]

    if as_of is None:
        as_of, as_of_source = today, "mac_dinh_hom_nay"

    # Ghi đè mọi ô của lượt này — checkpoint còn giữ giá trị của lượt trước.
    return {
        "as_of_date": as_of.isoformat(),
        "as_of_source": as_of_source,
        "tax_types": tax_types,
        "question_kind": kind,
        "concept_term": None,
        "label_source": label_source,
        "search_text": search_text,
        "search_parts": [search_text],  # split_question ghi đè nếu tách
        "understand_usage": usage,
    }

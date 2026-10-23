"""Tách câu hỏi nhiều ý thành các câu tìm kiếm ngắn — mỗi ý tìm riêng (docs/architecture.md, Model AI).

Câu hỏi phân tích ("khoản chi nào được trừ, khoản nào bị loại, cần bổ sung hồ sơ gì, rủi ro truy thu, xử phạt") cần
5–6 mảng luật; tìm một lần với cả câu chỉ ra vài Điều của một hai mảng. Quy tắc trước (quy tắc bất biến số 12): câu
ngắn một ý, hoặc câu hỏi nối tiếp → giữ nguyên, không gọi model. Câu tách ra chỉ dùng để tìm, không đưa vào câu trả lời.

Chạy bài tự kiểm: python -m app.answer.split_question
"""

from app import config
from app.answer.call_local_model import ask_local_model_for_json

MAX_PARTS = 5
LONG_QUESTION_WORDS = 30  # câu trong bộ đo tìm kiếm dài nhất 17 từ — tạm, chưa đo
SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "cac_y": {"type": "array", "items": {"type": "string", "maxLength": 200}, "minItems": 1, "maxItems": MAX_PARTS},
    },
    "required": ["cac_y"],
    "additionalProperties": False,
}
SPLIT_PROMPT = (
    "Tách câu hỏi về thuế Việt Nam thành các ý cần tra trong văn bản luật. Mỗi ý là một câu tìm kiếm ngắn, dùng thuật "
    "ngữ của văn bản luật, ví dụ: \"Các khoản chi được trừ khi xác định thu nhập chịu thuế thu nhập doanh nghiệp\", "
    "\"Xử phạt hành vi khai sai dẫn đến thiếu số tiền thuế phải nộp\", \"Khai bổ sung hồ sơ khai thuế\". "
    f"Mỗi ý một mảng quy định khác nhau, tối đa {MAX_PARTS} ý. Không thêm thông tin câu hỏi không nêu. Chỉ trả JSON."
)


def needs_split(question: str) -> bool:
    """Câu dài hoặc hỏi nhiều câu — câu ngắn một ý tìm bằng cả câu như cũ."""
    return len(question.split()) > LONG_QUESTION_WORDS or question.count("?") >= 2


def clean_parts(parts: list[str], fallback: str) -> list[str]:
    """Bỏ ý rỗng, trùng; không còn ý nào → tìm bằng cả câu."""
    kept = list(dict.fromkeys(" ".join(part.split()) for part in parts if part.strip()))
    return kept[:MAX_PARTS] or [fallback]


async def split_question(state: dict) -> dict:
    """Node LangGraph. Trả các câu tìm kiếm — một câu nếu không cần tách."""
    question, search_text = state["question"], state["search_text"]
    if state.get("label_source") == "luot_truoc" or not needs_split(question):
        return {"search_parts": [search_text], "split_usage": []}
    result, usage = await ask_local_model_for_json(
        [{"role": "system", "content": SPLIT_PROMPT}, {"role": "user", "content": question}],
        SPLIT_SCHEMA, temperature=config.LLM_CLASSIFY_TEMPERATURE, max_tokens=400,
    )
    return {"search_parts": clean_parts(result["cac_y"], search_text),
            "split_usage": [{**usage, "step": "split_question"}]}


def self_check() -> None:
    assert not needs_split("Nộp hồ sơ khai thuế chậm 75 ngày thì bị phạt bao nhiêu?")
    assert needs_split("Hóa đơn điện tử là gì? Khi nào phải lập hóa đơn?")
    assert needs_split(" ".join(["chi phí"] * 20))
    assert clean_parts(["  Khai bổ sung  hồ sơ ", "Khai bổ sung hồ sơ", ""], "cả câu") == ["Khai bổ sung hồ sơ"]
    assert clean_parts(["", "  "], "cả câu") == ["cả câu"]
    assert len(clean_parts([str(i) for i in range(9)], "x")) == MAX_PARTS
    print("PASS")


if __name__ == "__main__":
    self_check()

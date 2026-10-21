"""Model viết câu trả lời theo JSON schema: kết luận + căn cứ trích nguyên văn, chỉ từ các Điều được đưa vào.

Căn cứ trỏ tới số thứ tự đoạn [1], [2]… thay vì tự ghi số hiệu văn bản — model không bịa được số hiệu.
Không tìm được Điều nào → không gọi model, trả "không có căn cứ" (guardrail d, docs/danh-gia.md).
"""

from app import config
from app.answer.call_local_model import ask_local_model_for_json
from app.answer.search_articles import load_chunk_texts

MAX_CHARS_PER_ARTICLE = 6000  # Điều dài nhất 473.833 ký tự — cắt để vừa context 16K token

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "co_can_cu": {"type": "boolean"},
        "ket_luan": {"type": "string"},
        "can_cu": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {"doan": {"type": "integer"}, "trich_dan": {"type": "string"}},
                "required": ["doan", "trich_dan"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["co_can_cu", "ket_luan", "can_cu"],
    "additionalProperties": False,
}
SYSTEM_PROMPT = (
    "Bạn là trợ lý tra cứu pháp luật thuế Việt Nam cho một kế toán. Chỉ dùng các đoạn văn bản luật được đánh số "
    "[1], [2]… bên dưới; không dùng hiểu biết riêng.\n"
    "- ket_luan: trả lời ngắn gọn, đúng đối tượng mà câu hỏi nói tới. Đọc kỹ mỗi khoản áp dụng cho ai — không lấy "
    "quy định của đối tượng này áp cho đối tượng khác.\n"
    "- can_cu: mỗi căn cứ ghi số đoạn (doan) và trich_dan là câu CHÉP NGUYÊN VĂN từ đoạn đó, không sửa một chữ.\n"
    "- Nếu một khoản chỉ dẫn sang văn bản khác mà văn bản đó không có trong các đoạn, nói rõ cần xem văn bản đó.\n"
    "- Không có căn cứ trong các đoạn thì co_can_cu = false, can_cu rỗng, ket_luan nói không có căn cứ.\n"
    "- Câu hỏi là vi phạm, xử phạt: trình bày theo dạng nếu–thì, không kết luận ai đã vi phạm."
)


def format_context(articles: list[dict], texts: dict[int, str]) -> str:
    blocks = []
    for number, article in enumerate(articles, start=1):
        text = texts[article["chunk_id"]]
        cut_note = " (đã cắt bớt)" if len(text) > MAX_CHARS_PER_ARTICLE else ""
        blocks.append(
            f"[{number}] {article['loai']} {article['so_hieu']} — Điều {article['dieu_so']}. "
            f"{article['dieu_ten'] or ''}{cut_note}\n{text[:MAX_CHARS_PER_ARTICLE]}"
        )
    return "\n\n".join(blocks)


async def write_answer(state: dict) -> dict:
    """Node LangGraph."""
    articles = state.get("articles") or []
    if not articles:
        draft = {"co_can_cu": False, "ket_luan": "Không tìm thấy Điều luật nào phù hợp trong dữ liệu.", "can_cu": []}
        return {"draft": draft, "write_usage": []}

    texts = await load_chunk_texts([a["chunk_id"] for a in articles])
    question = (
        f"Mốc thời gian: {state['as_of_date']}\n\nCác đoạn văn bản luật:\n{format_context(articles, texts)}"
        f"\n\nCâu hỏi: {state['question']}"
    )
    draft, usage = await ask_local_model_for_json(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
        ANSWER_SCHEMA, temperature=config.LLM_ANSWER_TEMPERATURE, max_tokens=config.LLM_ANSWER_MAX_TOKENS,
    )
    return {"draft": draft, "write_usage": [{**usage, "step": "write_answer"}]}

"""Model viết câu trả lời theo JSON schema: kết luận + căn cứ trích nguyên văn, chỉ từ các Điều được đưa vào.

Căn cứ trỏ tới số thứ tự đoạn [1], [2]… thay vì tự ghi số hiệu văn bản — model không bịa được số hiệu.
Không tìm được Điều nào → không gọi model, trả "không có căn cứ" (guardrail d, docs/danh-gia.md).
"""

from app import config
from app.answer.call_local_model import ask_local_model_for_json
from app.answer.search_articles import expiry_note, load_chunk_texts, provision_label

MAX_CHARS_PER_ARTICLE = 6000  # Điều dài nhất 473.833 ký tự — cắt để vừa context 16K token
MAX_REFERENCED_CHARS = 3000  # Điều được dẫn chiếu: chỉ để model thấy nửa còn lại của quy định
# Tổng chữ luật đưa model (4 × 6.000 + 2 × 3.000 như trước) — câu nhiều ý có tới 8 Điều thì mỗi Điều được ít chữ hơn
CONTEXT_CHAR_BUDGET = 30000
# Model từng chép cả khoản dài hàng nghìn ký tự vào một trích dẫn và chạm max_tokens (câu nhiều ý, 23/10/2026) —
# schema chặn cứng (grammar của llama.cpp), prompt dặn chép câu ngắn nhất đủ làm căn cứ
MAX_QUOTE_CHARS = 400  # 600 vẫn bị chép nhảy cóc giữa khoản

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "co_can_cu": {"type": "boolean"},
        "ket_luan": {"type": "string"},
        "can_cu": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {"doan": {"type": "integer"},
                               "trich_dan": {"type": "string", "maxLength": MAX_QUOTE_CHARS}},
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
    "- can_cu: mỗi căn cứ ghi số đoạn (doan) và trich_dan là câu CHÉP NGUYÊN VĂN từ đoạn đó, không sửa một chữ — "
    "chỉ một hai câu ngắn nhất đủ làm căn cứ, không chép cả khoản.\n"
    "- Đoạn ghi ĐÃ HẾT HIỆU LỰC: ưu tiên đoạn còn hiệu lực; chỉ dùng khi không có đoạn nào khác, và nói rõ văn bản đó đã hết hiệu lực.\n"
    "- Nếu một khoản chỉ dẫn sang văn bản khác mà văn bản đó không có trong các đoạn, nói rõ cần xem văn bản đó.\n"
    "- Không có căn cứ trong các đoạn thì co_can_cu = false, can_cu rỗng, ket_luan nói không có căn cứ.\n"
    "- Câu hỏi là vi phạm, xử phạt: trình bày theo dạng nếu–thì, không kết luận ai đã vi phạm.\n"
    "- Câu hỏi gồm nhiều ý: tung_y trả lời lần lượt từng ý đã liệt kê, mỗi ý vài câu, dựa trên các đoạn. Dữ kiện câu hỏi chưa nêu thì chia trường hợp nếu–thì và nói rõ cần "
    "thêm dữ kiện gì; không giả định dữ kiện chưa có."
)


def answer_schema(part_count: int) -> dict:
    """Câu nhiều ý (split_question): schema buộc đúng một câu trả lời cho mỗi ý — model 4B được dặn bằng lời thì vẫn
    chỉ viết một câu chung chung (đo 23/10/2026)."""
    if part_count <= 1:
        return ANSWER_SCHEMA
    each_part = {"type": "array", "minItems": part_count, "maxItems": part_count,
                 "items": {"type": "object", "properties": {"tra_loi": {"type": "string"}},
                           "required": ["tra_loi"], "additionalProperties": False}}
    properties = {"co_can_cu": ANSWER_SCHEMA["properties"]["co_can_cu"], "tung_y": each_part,
                  "can_cu": ANSWER_SCHEMA["properties"]["can_cu"]}
    return {**ANSWER_SCHEMA, "properties": properties, "required": ["co_can_cu", "tung_y", "can_cu"]}


def format_context(articles: list[dict], texts: dict[int, str]) -> str:
    per_article = CONTEXT_CHAR_BUDGET // max(len(articles), 1)
    blocks = []
    for number, article in enumerate(articles, start=1):
        text, limit, note = texts[article["chunk_id"]], min(MAX_CHARS_PER_ARTICLE, per_article), ""
        if reference := article.get("dan_chieu"):  # Điều được dẫn chiếu (add_referenced_articles): chỉ khoản được nhắc
            if reference["vi_tri"]:
                start, end = reference["vi_tri"]
                text = text[start:end]
                note = f", khoản {reference['khoan']}"
            limit = min(MAX_REFERENCED_CHARS, per_article)
            note += f", được dẫn chiếu từ đoạn [{reference['tu_doan']}]"
        if article.get("het_hieu_luc"):
            note += f". ĐÃ HẾT HIỆU LỰC: {expiry_note(article['het_hieu_luc'])}"
        cut_note = " (đã cắt bớt)" if len(text) > limit else ""
        blocks.append(
            f"[{number}] {article['loai']} {article['so_hieu']} — {provision_label(article['dieu_level'], article['dieu_so'])}. "
            f"{article['dieu_ten'] or ''}{note}{cut_note}\n{text[:limit]}"
        )
    return "\n\n".join(blocks)


async def write_answer(state: dict) -> dict:
    """Node LangGraph."""
    articles = state.get("articles") or []
    if not articles:
        draft = {"co_can_cu": False, "ket_luan": "Không tìm thấy Điều luật nào phù hợp trong dữ liệu.", "can_cu": []}
        return {"draft": draft, "write_usage": []}

    texts = await load_chunk_texts([a["chunk_id"] for a in articles])
    parts = state.get("search_parts") or []
    question = (
        f"Mốc thời gian: {state['as_of_date']}\n\nCác đoạn văn bản luật:\n{format_context(articles, texts)}"
        f"\n\nCâu hỏi: {state['question']}"
    )
    if len(parts) > 1:
        question += "\n\nCác ý cần trả lời, theo đúng thứ tự trong tung_y:\n" + "\n".join(
            f"{number}. {part}" for number, part in enumerate(parts, start=1))
    draft, usage = await ask_local_model_for_json(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
        # câu nhiều ý trả lời dài hơn; giới hạn vẫn chặn lặp vô tận
        answer_schema(len(parts)), temperature=config.LLM_ANSWER_TEMPERATURE,
        max_tokens=config.LLM_ANSWER_MAX_TOKENS * (2 if len(parts) > 1 else 1),
    )
    if "tung_y" in draft:  # ghép thành một kết luận — các bước kiểm và giao diện chỉ đọc ket_luan
        draft["ket_luan"] = "\n\n".join(
            f"{number}. {part}: {item['tra_loi']}" for number, (part, item) in enumerate(zip(parts, draft["tung_y"]), 1))
    return {"draft": draft, "write_usage": [{**usage, "step": "write_answer"}]}

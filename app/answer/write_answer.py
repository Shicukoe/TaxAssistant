"""Model viết câu trả lời theo JSON schema: kết luận + căn cứ trích nguyên văn, chỉ từ các Điều được đưa vào.

Căn cứ trỏ tới số thứ tự đoạn [1], [2]… thay vì tự ghi số hiệu văn bản — model không bịa được số hiệu.
Không tìm được Điều nào → không gọi model, trả "không có căn cứ" (guardrail d, docs/danh-gia.md).

Kết luận chạy ra từng chữ (docs/architecture.md, Model AI): đọc dần chuỗi JSON model đang viết, lấy phần kết luận (hoặc
từng ý) và đẩy ra bằng get_stream_writer của LangGraph — giao diện ghi rõ "chưa kiểm căn cứ" cho tới khi kiểm xong.

Chạy bài tự kiểm: python -m app.answer.write_answer
"""

import re

from langgraph.config import get_stream_writer

from app import config
from app.answer.call_local_model import stream_local_model_json
from app.answer.search_articles import expiry_note, load_chunk_texts, provision_label

MAX_CHARS_PER_ARTICLE = 6000  # Điều dài nhất 473.833 ký tự — cắt để vừa context 16K token
MAX_REFERENCED_CHARS = 3000  # Điều được dẫn chiếu: chỉ để model thấy nửa còn lại của quy định
# Tổng chữ luật đưa model (4 × 6.000 + 2 × 3.000 như trước) — câu nhiều ý có tới 8 Điều thì mỗi Điều được ít chữ hơn
CONTEXT_CHAR_BUDGET = 30000
# Giới hạn độ dài trích dẫn: không giới hạn thì model chép cả khoản dài và chạm max_tokens; trích dài cũng hay bị
# chép nhảy cóc giữa khoản (trượt kiểm khớp nguyên văn). Schema chặn cứng (grammar của llama.cpp).
MAX_QUOTE_CHARS = 400

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
    """Câu nhiều ý (split_question): schema buộc đúng một câu trả lời cho mỗi ý — chỉ dặn bằng lời thì model 4B
    thường gộp thành một câu chung chung."""
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
            note += (f", được dẫn chiếu từ đoạn [{reference['tu_doan']}]" if reference["tu_doan"]
                     else ", quy định chấm dứt khoản thu — văn bản về khoản thu đó không còn áp dụng")
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
    if notes := state.get("calendar_notes"):  # add_deadline_rule: thời hạn rơi vào ngày nghỉ, code tính sẵn
        question += ("\n\nLịch đã tính sẵn, đúng — dùng làm dữ kiện: thời hạn trong đoạn luật rơi vào ngày nghỉ thì "
                     "ngày cuối cùng là ngày làm việc liền kề sau, theo đoạn quy định về ngày nghỉ ở trên. Câu hỏi nêu "
                     "một ngày thì so ngày đó với thời hạn sau khi lùi, trả lời đúng hay sai và trích cả đoạn thời hạn "
                     "lẫn đoạn quy định về ngày nghỉ:\n" + "\n".join(f"- {note['ghi_chu']}" for note in notes))
    if len(parts) > 1:
        question +="\n\nCác ý cần trả lời, theo đúng thứ tự trong tung_y:\n" + "\n".join(
            f"{number}. {part}" for number, part in enumerate(parts, start=1))
    write = stream_writer()
    shown = ""

    def show_progress(raw: str) -> None:
        nonlocal shown
        text = live_conclusion(raw, parts)
        if text != shown:
            shown = text
            write({"dang_viet": text})

    draft, usage = await stream_local_model_json(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
        # câu nhiều ý trả lời dài hơn; giới hạn vẫn chặn lặp vô tận
        answer_schema(len(parts)), temperature=config.LLM_ANSWER_TEMPERATURE,
        max_tokens=config.LLM_ANSWER_MAX_TOKENS * (2 if len(parts) > 1 else 1), on_text=show_progress,
    )
    if "tung_y" in draft:  # ghép thành một kết luận — các bước kiểm và giao diện chỉ đọc ket_luan
        draft["ket_luan"] = join_parts(parts, [item["tra_loi"] for item in draft["tung_y"]])
    return {"draft": draft, "write_usage": [{**usage, "step": "write_answer"}]}


def join_parts(parts: list[str], answers: list[str]) -> str:
    """Câu nhiều ý: "1. <ý>: <trả lời>" — cùng một cách ghép cho bản đang viết và bản cuối."""
    return "\n\n".join(f"{number}. {part}: {answer}" for number, (part, answer) in enumerate(zip(parts, answers), 1))


def partial_json_strings(raw: str, key: str) -> list[str]:
    """Giá trị (có thể còn dở) của mọi chuỗi "key": "…" trong JSON đang viết. Dừng ở dấu " đóng hoặc ở cuối chữ;
    bỏ escape còn dở ở cuối. \\u của nửa cặp surrogate bị bỏ — không mã hoá được ra UTF-8."""
    values = []
    for match in re.finditer(rf'"{key}"\s*:\s*"', raw):
        position, chars = match.end(), []
        while position < len(raw) and raw[position] != '"':
            char = raw[position]
            if char != "\\":
                chars.append(char)
                position += 1
                continue
            if position + 1 >= len(raw):
                break
            escaped = raw[position + 1]
            if escaped == "u":
                if position + 6 > len(raw):
                    break
                code = int(raw[position + 2:position + 6], 16)
                if not 0xD800 <= code <= 0xDFFF:
                    chars.append(chr(code))
                position += 6
                continue
            chars.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}.get(escaped, escaped))
            position += 2
        values.append("".join(chars))
    return values


def live_conclusion(raw: str, parts: list[str]) -> str:
    """Kết luận đang viết từ JSON dở: ket_luan, hoặc các tra_loi của câu nhiều ý."""
    if len(parts) > 1:
        answers = partial_json_strings(raw, "tra_loi")
        return join_parts(parts, answers) if answers else ""
    return next(iter(partial_json_strings(raw, "ket_luan")), "")


def stream_writer():
    """Gửi bản đang viết ra stream_mode="custom" của LangGraph; gọi node ngoài đồ thị (bài đo, script) → bỏ qua."""
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _: None


def self_check() -> None:
    raw = '{\n  "co_can_cu": true,\n  "ket_luan": "Phạt từ 8.000.000 \\"đồng\\"\\nđến 15'
    assert live_conclusion(raw, []) == 'Phạt từ 8.000.000 "đồng"\nđến 15', live_conclusion(raw, [])
    assert live_conclusion(raw + "\\", []) == 'Phạt từ 8.000.000 "đồng"\nđến 15', "escape dở ở cuối bị bỏ"
    assert live_conclusion('{"ket_luan": "Thu\\u1ebf', []) == "Thuế"
    assert live_conclusion('{"co_can_cu": tr', []) == ""
    raw = '{"co_can_cu": true, "tung_y": [{"tra_loi": "Được trừ."}, {"tra_loi": "Phạt 2'
    assert live_conclusion(raw, ["Chi phí", "Xử phạt"]) == "1. Chi phí: Được trừ.\n\n2. Xử phạt: Phạt 2"
    assert join_parts(["A"], ["x"]) == "1. A: x"
    print("PASS")


if __name__ == "__main__":
    self_check()

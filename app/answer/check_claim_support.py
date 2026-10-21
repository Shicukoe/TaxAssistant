"""Guardrail g: mỗi câu trong kết luận phải được căn cứ ủng hộ (docs/danh-gia.md, mục 6).

Làm theo cách của AlignScore (Zha và cộng sự, ACL 2023): ngữ cảnh cắt thành đoạn ~350 token, câu khẳng định cắt
thành từng câu; mỗi câu lấy điểm cao nhất trên các đoạn, điểm cả câu trả lời là trung bình. AlignScore chỉ có bản
tiếng Anh → hàm chấm là model NLI đa ngôn ngữ (config.NLI_MODEL), xác suất nhãn "entailment".

Ngữ cảnh = chữ của KHOẢN chứa mỗi trích dẫn đã qua kiểm (guardrail a), không chỉ câu trích — khoản 4 "áp dụng cho
ai" nằm ở câu dẫn của khoản. Bắt lỗi "suy luận sai": trích đúng nguyên văn nhưng áp cho đối tượng khác.
Câu dưới ngưỡng chỉ bị gắn cờ, không xoá câu trả lời. Chạy CPU: không tranh VRAM với llama-server.
"""

import asyncio
import re
from functools import lru_cache

import psycopg

from app import config
from app.answer.search_articles import load_chunk_texts

CHUNK_TOKENS = 350  # theo AlignScore
SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+(?=[A-ZĐÀ-Ỹ0-9\"“(-])")


@lru_cache(maxsize=1)
def load_nli_model():
    """Nạp một lần cho cả tiến trình (~560 MB, vài giây trên CPU). Import muộn để app khởi động nhanh."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(config.NLI_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(config.NLI_MODEL).eval()
    # Lấy chỉ số nhãn từ config của model, không đoán thứ tự.
    labels = {name.lower(): index for index, name in model.config.id2label.items()}
    return torch, tokenizer, model, labels["entailment"], labels["contradiction"]


def split_sentences(text: str) -> list[str]:
    """Tách câu tiếng Việt đơn giản. Không tách ở dấu phẩy: '1,5 lít' là một con số."""
    return [s.strip() for s in SENTENCE_END.split(text) if len(s.strip()) >= 15]


def split_into_chunks(text: str, tokenizer) -> list[str]:
    """Gộp câu thành đoạn tối đa ~350 token."""
    chunks, current, current_tokens = [], [], 0
    for sentence in split_sentences(text) or [text]:
        tokens = len(tokenizer(sentence, add_special_tokens=False)["input_ids"])
        if current and current_tokens + tokens > CHUNK_TOKENS:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += tokens
    if current:
        chunks.append(" ".join(current))
    return chunks


def score_claims(claims: list[str], context: str) -> list[dict]:
    """Mỗi câu: điểm ủng hộ = max P(entailment) trên các đoạn; kèm P(contradiction) của đoạn đó."""
    torch, tokenizer, model, entail_index, contradict_index = load_nli_model()
    chunks = split_into_chunks(context, tokenizer)
    results = []
    with torch.inference_mode():
        for claim in claims:
            inputs = tokenizer(chunks, [claim] * len(chunks), truncation="only_first", max_length=512,
                               padding=True, return_tensors="pt")
            probabilities = torch.softmax(model(**inputs).logits, dim=-1)
            best = int(torch.argmax(probabilities[:, entail_index]))
            results.append({
                "cau": claim,
                "diem_ung_ho": round(float(probabilities[best, entail_index]), 3),
                "diem_mau_thuan": round(float(probabilities[best, contradict_index]), 3),
            })
    return results


async def load_clause_context(citations: list[dict]) -> str:
    """Chữ của khoản (không có khoản thì Điều) chứa mỗi trích dẫn đã qua kiểm, bỏ trùng."""
    verified = [c for c in citations if c.get("trang_thai") == "dat"]
    texts = await load_chunk_texts(list({c["chunk_id"] for c in verified}))
    pieces = []
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        for citation in verified:
            cursor = await conn.execute(
                "select char_start, char_end from chunk_positions "
                "where chunk_id = %s and level in ('khoan', 'dieu') and char_start <= %s and %s < char_end "
                "order by (level = 'khoan') desc, char_end - char_start limit 1",
                (citation["chunk_id"], citation["vi_tri_ky_tu"], citation["vi_tri_ky_tu"]),
            )
            span = await cursor.fetchone()
            text = texts[citation["chunk_id"]]
            piece = text[span[0]:span[1]] if span else citation["trich_dan"]
            if piece not in pieces:
                pieces.append(piece)
    return "\n".join(pieces)


async def check_claim_support(state: dict) -> dict:
    """Node LangGraph. Không có căn cứ đã qua kiểm thì không có gì để chấm."""
    if not state.get("has_cause"):
        return {"claim_support": [], "support_score": None}
    claims = split_sentences(state["draft"].get("ket_luan", ""))
    context = await load_clause_context(state["citations"])
    if not claims or not context:
        return {"claim_support": [], "support_score": None}
    results = await asyncio.to_thread(score_claims, claims, context)  # model đồng bộ → chạy ở thread riêng
    for result in results:
        result["dat"] = result["diem_ung_ho"] >= config.NLI_SUPPORT_THRESHOLD
    support_score = round(sum(r["diem_ung_ho"] for r in results) / len(results), 3)
    warnings = [f"⚠ Câu chưa được căn cứ ủng hộ (điểm {r['diem_ung_ho']}): \"{r['cau']}\"" for r in results
                if not r["dat"]]
    # Chế độ đo: chưa hiện cảnh báo cho tới khi ngưỡng được hiệu chỉnh trên tập kiểm định (config.NLI_WARNINGS_VISIBLE).
    visible = warnings if config.NLI_WARNINGS_VISIBLE else []
    answer_text = state["answer_text"] + ("\n" + "\n".join(visible) if visible else "")
    return {"claim_support": results, "support_score": support_score, "answer_text": answer_text}

"""Nối các bước của luồng trả lời bằng LangGraph (docs/architecture.md, mục Model AI).

hiểu câu hỏi → tách câu nhiều ý → tìm Điều → kéo Điều được dẫn chiếu (và khoản chấm dứt khoản thu) → thời hạn rơi
vào ngày nghỉ → viết trả lời → kiểm trích dẫn → kiểm câu kết luận có được căn cứ ủng hộ → lưu.
Rẽ nhánh sau bước hiểu câu hỏi (loại nhận bằng quy tắc): chào hỏi → câu mẫu → lưu; khái niệm → tra định nghĩa
→ kiểm trích dẫn (không thấy định nghĩa → tìm thường). Cạnh có điều kiện nhưng đồ thị cố định, không phải agent.
Mỗi cuộc hội thoại là một thread_id; checkpointer Postgres giữ trạng thái giữa các lượt (hỏi nối tiếp). Chỉ node cuối ghi questions/answers/usage_log/model_calls — đó là bản ghi chính thức.
"""

import json
import time
from typing import TypedDict

import httpx
import psycopg
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app import config
from app.answer.add_deadline_rule import add_deadline_rule
from app.answer.add_referenced_articles import add_referenced_articles
from app.answer.answer_simple_questions import look_up_definition, reply_small_talk
from app.answer.check_citations import check_citations
from app.answer.check_claim_support import check_claim_support
from app.answer.search_articles import search_articles
from app.answer.split_question import split_question
from app.answer.understand_question import CONCEPT, SMALL_TALK, understand_question
from app.answer.write_answer import write_answer


class AnswerState(TypedDict, total=False):
    thread_id: str
    question: str
    started_at: float  # time.time() lúc nhận câu hỏi — tổng thời gian trả lời ghi vào answers.duration_ms
    # hiểu câu hỏi — các "ô" mang sang lượt sau
    as_of_date: str
    as_of_source: str
    tax_types: list[str]
    question_kind: str
    concept_term: str | None  # thuật ngữ đã bỏ dấu của câu hỏi khái niệm ("thue")
    label_source: str
    search_text: str
    search_parts: list[str]  # câu nhiều ý → các câu tìm kiếm (split_question); một ý → [search_text]
    # tìm, viết, kiểm
    articles: list[dict]
    ceased_sources: list[dict]  # chỗ tuyên bố chấm dứt khoản thu của các ứng viên (search_articles)
    calendar_notes: list[dict]  # thời hạn rơi vào ngày nghỉ (add_deadline_rule): ngày, ngày lùi, ghi chú
    search_warning: str | None  # tìm theo nghĩa lỗi (server embedding tắt) → chỉ còn từ khoá
    draft: dict
    citations: list[dict]
    unverified_numbers: list[str]
    has_cause: bool
    claim_support: list[dict]  # guardrail g: điểm ủng hộ từng câu kết luận
    support_score: float | None
    claim_unscored: int  # câu kết luận chưa kịp chấm (giới hạn thời gian của guardrail g)
    answer_text: str
    # token, thời gian, request và chữ trả về của từng lời gọi model — ghi usage_log, model_calls ở bước cuối
    understand_usage: list[dict]
    split_usage: list[dict]
    write_usage: list[dict]
    question_id: int
    answer_id: int


def is_connection_error(error: Exception) -> bool:
    """Chỉ thử lại lỗi kết nối — không thử lại khi model trả lời kém (docs/code-standards.md)."""
    return isinstance(error, (httpx.ConnectError, httpx.RemoteProtocolError, psycopg.OperationalError))


async def save_answer(state: AnswerState) -> dict:
    """Node cuối: ghi bản ghi chính thức trong một transaction. Cuộc hội thoại từ web đã có chủ (server nhận chủ
    trước khi chạy luồng); từ terminal thì tạo ở đây, không chủ."""
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        async with conn.transaction():
            await conn.execute("insert into conversations (thread_id) values (%s) on conflict (thread_id) do nothing",
                               (state["thread_id"],))
            cursor = await conn.execute(
                "insert into questions (text, kind, sac_thue, as_of_date, thread_id) "
                "values (%s, %s, %s, %s, %s) returning id",
                (state["question"], state["question_kind"], ",".join(state["tax_types"]),
                 state["as_of_date"], state["thread_id"]),
            )
            question_id = (await cursor.fetchone())[0]
            cursor = await conn.execute(
                "insert into answers (question_id, text, ket_luan, model, has_cause, citations, duration_ms) "
                "values (%s, %s, %s, %s, %s, %s, %s) returning id",
                (question_id, state["answer_text"], (state.get("draft") or {}).get("ket_luan"), config.LLM_MODEL,
                 state["has_cause"], json.dumps(state["citations"], ensure_ascii=False),
                 round((time.time() - state["started_at"]) * 1000) if state.get("started_at") else None),
            )
            answer_id = (await cursor.fetchone())[0]
            for usage in state.get("understand_usage", []) + state.get("split_usage", []) + state.get("write_usage", []):
                await conn.execute(
                    "insert into usage_log (question_id, model, input_tokens, output_tokens, duration_ms) "
                    "values (%s, %s, %s, %s, %s)",
                    (question_id, usage["model"], usage["input_tokens"], usage["output_tokens"], usage["duration_ms"]),
                )
                await conn.execute(
                    "insert into model_calls (question_id, step, model, request, output) values (%s, %s, %s, %s, %s)",
                    (question_id, usage["step"], usage["model"], json.dumps(usage["request"], ensure_ascii=False),
                     usage["output"]),
                )
    return {"question_id": question_id, "answer_id": answer_id}


def route_after_understanding(state: AnswerState) -> str:
    return {SMALL_TALK: "reply_small_talk", CONCEPT: "look_up_definition"}.get(state["question_kind"], "split_question")


def route_after_definition(state: AnswerState) -> str:
    return "check_citations" if state.get("articles") else "search_articles"


def build_answer_graph(checkpointer):
    retry = RetryPolicy(max_attempts=3, retry_on=is_connection_error)
    model_timeout = config.LLM_TIMEOUT_SECONDS + 10
    builder = StateGraph(AnswerState)
    builder.add_node("understand_question", understand_question, retry_policy=retry, timeout=model_timeout)
    builder.add_node("reply_small_talk", reply_small_talk)
    builder.add_node("look_up_definition", look_up_definition, retry_policy=retry, timeout=30)
    builder.add_node("split_question", split_question, retry_policy=retry, timeout=model_timeout)
    builder.add_node("search_articles", search_articles, retry_policy=retry, timeout=60)
    builder.add_node("add_referenced_articles", add_referenced_articles, retry_policy=retry, timeout=30)
    builder.add_node("add_deadline_rule", add_deadline_rule, retry_policy=retry, timeout=30)
    builder.add_node("write_answer", write_answer, retry_policy=retry, timeout=model_timeout)
    builder.add_node("check_citations", check_citations, retry_policy=retry, timeout=30)
    # nạp model NLI lần đầu mất vài giây trên CPU
    builder.add_node("check_claim_support", check_claim_support, retry_policy=retry, timeout=120)
    builder.add_node("save_answer", save_answer, retry_policy=retry, timeout=30)
    builder.add_edge(START, "understand_question")
    builder.add_conditional_edges("understand_question", route_after_understanding,
                                  ["reply_small_talk", "look_up_definition", "split_question"])
    builder.add_edge("split_question", "search_articles")
    builder.add_edge("reply_small_talk", "save_answer")
    builder.add_conditional_edges("look_up_definition", route_after_definition, ["check_citations", "search_articles"])
    builder.add_edge("search_articles", "add_referenced_articles")
    builder.add_edge("add_referenced_articles", "add_deadline_rule")
    builder.add_edge("add_deadline_rule", "write_answer")
    builder.add_edge("write_answer", "check_citations")
    builder.add_edge("check_citations", "check_claim_support")
    builder.add_edge("check_claim_support", "save_answer")
    builder.add_edge("save_answer", END)
    return builder.compile(checkpointer=checkpointer)

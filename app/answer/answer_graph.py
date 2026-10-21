"""Nối các bước của luồng trả lời bằng LangGraph (docs/architecture.md, mục Model AI).

hiểu câu hỏi → tìm Điều → viết trả lời → kiểm trích dẫn → kiểm câu kết luận có được căn cứ ủng hộ → lưu
Cạnh cố định, không phải agent. Mỗi cuộc hội thoại là một thread_id; checkpointer Postgres giữ trạng thái giữa
các lượt (hỏi nối tiếp). Chỉ node cuối ghi questions/answers/usage_log — đó là bản ghi chính thức.
"""

import json
from typing import TypedDict

import httpx
import psycopg
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app import config
from app.answer.check_citations import check_citations
from app.answer.check_claim_support import check_claim_support
from app.answer.search_articles import search_articles
from app.answer.understand_question import understand_question
from app.answer.write_answer import write_answer


class AnswerState(TypedDict, total=False):
    thread_id: str
    question: str
    # hiểu câu hỏi — các "ô" mang sang lượt sau
    as_of_date: str
    as_of_source: str
    tax_types: list[str]
    question_kind: str
    label_source: str
    search_text: str
    # tìm, viết, kiểm
    articles: list[dict]
    draft: dict
    citations: list[dict]
    unverified_numbers: list[str]
    has_cause: bool
    claim_support: list[dict]  # guardrail g: điểm ủng hộ từng câu kết luận
    support_score: float | None
    answer_text: str
    # token + thời gian của từng lời gọi model, ghi vào usage_log ở bước cuối
    understand_usage: list[dict]
    write_usage: list[dict]
    question_id: int


def is_connection_error(error: Exception) -> bool:
    """Chỉ thử lại lỗi kết nối — không thử lại khi model trả lời kém (docs/code-standards.md)."""
    return isinstance(error, (httpx.ConnectError, httpx.RemoteProtocolError, psycopg.OperationalError))


async def save_answer(state: AnswerState) -> dict:
    """Node cuối: ghi bản ghi chính thức trong một transaction."""
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        async with conn.transaction():
            cursor = await conn.execute(
                "insert into questions (text, kind, sac_thue, as_of_date, thread_id) "
                "values (%s, %s, %s, %s, %s) returning id",
                (state["question"], state["question_kind"], ",".join(state["tax_types"]),
                 state["as_of_date"], state["thread_id"]),
            )
            question_id = (await cursor.fetchone())[0]
            await conn.execute(
                "insert into answers (question_id, text, model, has_cause, citations) values (%s, %s, %s, %s, %s)",
                (question_id, state["answer_text"], config.LLM_MODEL, state["has_cause"],
                 json.dumps(state["citations"], ensure_ascii=False)),
            )
            for usage in state.get("understand_usage", []) + state.get("write_usage", []):
                await conn.execute(
                    "insert into usage_log (question_id, model, input_tokens, output_tokens, duration_ms) "
                    "values (%s, %s, %s, %s, %s)",
                    (question_id, usage["model"], usage["input_tokens"], usage["output_tokens"], usage["duration_ms"]),
                )
    return {"question_id": question_id}


def build_answer_graph(checkpointer):
    retry = RetryPolicy(max_attempts=3, retry_on=is_connection_error)
    model_timeout = config.LLM_TIMEOUT_SECONDS + 10
    builder = StateGraph(AnswerState)
    builder.add_node("understand_question", understand_question, retry_policy=retry, timeout=model_timeout)
    builder.add_node("search_articles", search_articles, retry_policy=retry, timeout=30)
    builder.add_node("write_answer", write_answer, retry_policy=retry, timeout=model_timeout)
    builder.add_node("check_citations", check_citations, retry_policy=retry, timeout=30)
    # nạp model NLI lần đầu mất vài giây trên CPU
    builder.add_node("check_claim_support", check_claim_support, retry_policy=retry, timeout=120)
    builder.add_node("save_answer", save_answer, retry_policy=retry, timeout=30)
    builder.add_edge(START, "understand_question")
    builder.add_edge("understand_question", "search_articles")
    builder.add_edge("search_articles", "write_answer")
    builder.add_edge("write_answer", "check_citations")
    builder.add_edge("check_citations", "check_claim_support")
    builder.add_edge("check_claim_support", "save_answer")
    builder.add_edge("save_answer", END)
    return builder.compile(checkpointer=checkpointer)

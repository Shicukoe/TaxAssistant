"""Ghi dữ liệu hội thoại theo người: nhận chủ cuộc hội thoại, ẩn khỏi danh sách, đánh giá câu trả lời
(docs/architecture.md, Truy cập và phân quyền — mọi câu SQL có điều kiện chủ sở hữu).
"""

import psycopg

from app import config

VERDICTS = ("dung", "sai", "chua_du")  # ba nhãn của Magesh (docs/danh-gia.md)
MAX_NOTE_CHARS = 2000


async def claim_conversation(thread_id: str, user_id: int) -> bool:
    """Cuộc hội thoại mới → ghi chủ là người này. True nếu cuộc hội thoại thuộc người này (mới hoặc đã có, chưa ẩn).
    Cuộc hội thoại của người khác, không chủ (từ terminal), hay đã ẩn → False."""
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        await conn.execute("insert into conversations (thread_id, user_id) values (%s, %s) "
                           "on conflict (thread_id) do nothing", (thread_id, user_id))
        row = await (await conn.execute(
            "select 1 from conversations where thread_id = %s and user_id = %s and hidden_at is null",
            (thread_id, user_id))).fetchone()
    return row is not None


async def hide_conversation(thread_id: str, user_id: int) -> None:
    """Nút xoá trên web: ẩn khỏi danh sách, dữ liệu giữ cho fine-tune / đánh giá."""
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        await conn.execute("update conversations set hidden_at = now() "
                           "where thread_id = %s and user_id = %s and hidden_at is null", (thread_id, user_id))


async def save_feedback(answer_id: int, user_id: int, verdict: str, note: str) -> bool:
    """Ghi (hoặc ghi đè) đánh giá của người hỏi. False nếu câu trả lời không thuộc người này hoặc nhãn sai."""
    if verdict not in VERDICTS:
        return False
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION) as conn:
        row = await (await conn.execute(
            """insert into answer_feedback (answer_id, user_id, verdict, note)
               select a.id, c.user_id, %(verdict)s, %(note)s
               from answers a join questions q on q.id = a.question_id
                              join conversations c on c.thread_id = q.thread_id
               where a.id = %(answer_id)s and c.user_id = %(user_id)s
               on conflict (answer_id) do update
                   set verdict = excluded.verdict, note = excluded.note, updated_at = now()
               returning answer_id""",
            {"answer_id": answer_id, "user_id": user_id, "verdict": verdict,
             "note": note.strip()[:MAX_NOTE_CHARS] or None})).fetchone()
    return row is not None

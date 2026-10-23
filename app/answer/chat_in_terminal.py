"""Demo: chat trong terminal, in trạng thái sau từng bước để debug.

    bash scripts/chat_demo.sh          (cần bash scripts/run_model_server.sh đang chạy)

Lệnh trong lúc chat:  /moi — cuộc hội thoại mới   /lichsu — state sau từng bước của cuộc hội thoại này   /thoat
"""

import asyncio
import json
import sys
import time
import uuid

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app import config
from app.answer.answer_graph import build_answer_graph
from app.answer.check_claim_support import load_nli_model
from app.answer.search_articles import provision_label

# Ô nào in ra sau mỗi bước — đủ để thấy lỗi nằm ở bước nào (lấy sai thông tin / tìm sai / viết sai).
DEBUG_FIELDS = {
    "understand_question": ["as_of_date", "as_of_source", "tax_types", "question_kind", "label_source", "search_text"],
    "split_question": ["search_parts"],
    "search_articles": ["articles"],
    "add_referenced_articles": ["articles"],
    "add_deadline_rule": ["calendar_notes", "articles"],
    "write_answer": ["draft"],
    "check_citations": ["citations", "unverified_numbers", "has_cause"],
    "check_claim_support": ["claim_support", "support_score", "claim_unscored"],
    "save_answer": ["question_id"],
}


def print_step(node: str, update: dict, elapsed_ms: int) -> None:
    print(f"  ┌ [{node}] {elapsed_ms} ms", flush=True)
    for field in DEBUG_FIELDS.get(node, []):
        value = update.get(field)
        if field == "articles":
            for article in value or []:
                label = provision_label(article["dieu_level"], article["dieu_so"])
                print(f"  │ {article['score']:>7}  {article['loai']} {article['so_hieu']} — {label}. "
                      f"{(article['dieu_ten'] or '')[:60]}", flush=True)
            continue
        if field == "claim_support":
            for result in value or []:
                mark = "đạt" if result["dat"] else "KHÔNG ĐẠT"
                print(f"  │ {mark:<9} ủng hộ {result['diem_ung_ho']:.3f} mâu thuẫn {result['diem_mau_thuan']:.3f}: "
                      f"{result['cau'][:90]}", flush=True)
            continue
        if field == "citations":
            for citation in value or []:
                print(f"  │ citation [{citation['trang_thai']}] đoạn {citation.get('doan')} "
                      f"{citation.get('vi_tri', '')}: {citation['trich_dan'][:80]}", flush=True)
            continue
        print(f"  │ {field}: {json.dumps(value, ensure_ascii=False)[:300]}", flush=True)
    for usage in update.get("understand_usage", []) + update.get("write_usage", []):
        print(f"  │ model: {usage['input_tokens']} token vào, {usage['output_tokens']} token ra, "
              f"{usage['duration_ms']} ms", flush=True)


async def show_history(graph, run_config: dict) -> None:
    async for snapshot in graph.aget_state_history(run_config):
        step = snapshot.metadata.get("step")
        values = snapshot.values
        print(f"  step {step:>3}  tiếp theo: {list(snapshot.next) or '-'}  "
              f"câu hỏi: {values.get('question', '')[:50]!r}  mốc: {values.get('as_of_date')}  "
              f"loại: {values.get('tax_types')}", flush=True)


async def chat() -> None:
    async with AsyncPostgresSaver.from_conn_string(config.DATABASE_CONNECTION) as checkpointer:
        await checkpointer.setup()
        graph = build_answer_graph(checkpointer)
        # Nạp model NLI của guardrail g lúc khởi động (~10 giây trên CPU), không để câu hỏi đầu tiên phải chờ.
        print("Đang nạp model kiểm câu kết luận (guardrail g)...", flush=True)
        await asyncio.to_thread(load_nli_model)
        thread_id = str(uuid.uuid4())
        print(f"Cuộc hội thoại {thread_id[:8]}. Lệnh: /moi /lichsu /thoat", flush=True)
        while True:
            try:
                question = input("\nBạn: ").strip()
            except EOFError:
                break
            if not question:
                continue
            if question == "/thoat":
                break
            run_config = {"configurable": {"thread_id": thread_id}}
            if question == "/moi":
                thread_id = str(uuid.uuid4())
                print(f"Cuộc hội thoại mới {thread_id[:8]}", flush=True)
                continue
            if question == "/lichsu":
                await show_history(graph, run_config)
                continue

            started = time.perf_counter()
            last_update = None
            async for chunk in graph.astream({"question": question, "thread_id": thread_id, "started_at": time.time()},
                                             run_config, stream_mode="updates", durability="async"):
                for node, update in chunk.items():
                    print_step(node, update or {}, round((time.perf_counter() - started) * 1000))
                    if "answer_text" in (update or {}):  # check_claim_support có thể thêm cảnh báo
                        last_update = update
            print(f"\nBot ({round(time.perf_counter() - started, 1)} s):\n{last_update['answer_text']}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # psycopg async không chạy với ProactorEventLoop mặc định của Windows (tài liệu psycopg).
    asyncio.run(chat(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)

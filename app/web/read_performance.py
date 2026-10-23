"""Số liệu cho trang Hiệu năng (docs/ui-context.md): số câu đã hỏi, thời gian trả lời, bộ nhớ GPU, tốc độ model.

Thời gian trả lời là answers.duration_ms (migration 010) — từ lúc nhận câu hỏi tới lúc lưu, gồm cả tìm kiếm và các
bước kiểm; câu trả lời cũ để trống. Bộ nhớ GPU đọc bằng nvidia-smi, tốc độ đọc/sinh đọc từ /metrics của llama-server
(bật bằng --metrics trong scripts/run_model_server.sh). Thiếu nguồn nào thì trang ghi "không đọc được", không lỗi.
Số đếm và thời gian tính trên mọi tài khoản (không có chữ câu hỏi); danh sách câu gần đây chỉ có câu của người xem.
"""

import asyncio
import subprocess

import httpx
import psycopg
from psycopg.rows import dict_row

from app import config

BRANCH_SQL = "case q.kind when 'chao_hoi' then 'Chào hỏi' when 'khai_niem' then 'Khái niệm' else 'Câu hỏi thường' end"
COUNT_SQL = """
    select count(*) as tong,
           count(*) filter (where asked_at >= current_date) as hom_nay,
           count(*) filter (where asked_at >= now() - interval '7 days') as bay_ngay
    from questions"""
DURATION_SQL = f"""
    select {BRANCH_SQL} as nhanh, count(*) as so_cau,
           percentile_cont(0.5) within group (order by a.duration_ms) / 1000.0 as trung_vi,
           percentile_cont(0.9) within group (order by a.duration_ms) / 1000.0 as cham_nhat_10
    from answers a join questions q on q.id = a.question_id
    where a.duration_ms is not null
    group by 1 order by 2 desc"""
RECENT_SQL = f"""
    select q.asked_at, q.text, {BRANCH_SQL} as nhanh, a.duration_ms / 1000.0 as giay, a.has_cause,
           (select sum(u.duration_ms) from usage_log u where u.question_id = q.id) / 1000.0 as giay_model
    from questions q join conversations c on c.thread_id = q.thread_id
                     left join answers a on a.question_id = q.id
    where c.user_id = %s
    order by q.asked_at desc
    limit 20"""
# Tốc độ = tổng token ÷ tổng giây, từ các bộ đếm cộng dồn (TYPE counter) kể từ lúc llama-server khởi động. Không dùng
# gauge "llamacpp:prompt_tokens_seconds" (Average … throughput): số này chỉ tính từ lần đọc /metrics trước — đọc hai lần
# liền nhau ra 0.
SPEED_COUNTERS = {"doc": ("llamacpp:prompt_tokens_total", "llamacpp:prompt_seconds_total"),
                  "sinh": ("llamacpp:tokens_predicted_total", "llamacpp:tokens_predicted_seconds_total")}


def read_gpu_memory() -> dict | None:
    """{'ten', 'dung_mb', 'tong_mb'} của GPU đầu tiên, hoặc None nếu không có nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    name, used, total = (part.strip() for part in result.stdout.splitlines()[0].split(","))
    return {"ten": name, "dung_mb": int(used), "tong_mb": int(total)}


async def read_model_speed() -> dict | None:
    """{'doc', 'sinh'} token/giây của model viết, hoặc None nếu server tắt."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(config.LLM_BASE_URL.removesuffix("/v1") + "/metrics")
            response.raise_for_status()
    except httpx.HTTPError:
        return None
    values = {}
    for line in response.text.splitlines():
        name, _, value = line.partition(" ")
        if not name.startswith("#") and value:
            values[name] = float(value)
    speed = {key: round(values[tokens] / values[seconds]) for key, (tokens, seconds) in SPEED_COUNTERS.items()
             if values.get(seconds)}
    return speed or None


async def load_performance(user_id: int) -> dict:
    async with await psycopg.AsyncConnection.connect(config.DATABASE_CONNECTION, row_factory=dict_row) as conn:
        counts = await (await conn.execute(COUNT_SQL)).fetchone()
        durations = await (await conn.execute(DURATION_SQL)).fetchall()
        recent = await (await conn.execute(RECENT_SQL, (user_id,))).fetchall()
    gpu, speed = await asyncio.gather(asyncio.to_thread(read_gpu_memory), read_model_speed())
    return {"so_cau": counts, "thoi_gian": durations, "gan_day": recent, "gpu": gpu, "toc_do": speed}

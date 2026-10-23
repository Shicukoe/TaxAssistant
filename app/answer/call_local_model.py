"""Chỗ duy nhất gọi model (quy tắc bất biến số 7): llama-server qua API kiểu OpenAI — model viết (cổng 9931)
và model embedding BGE-M3 (cổng 9932).

Trả về nội dung cùng usage (token, thời gian chạy) để bước cuối của luồng ghi vào usage_log —
node không ghi database giữa chừng (docs/code-standards.md).
"""

import json
import time
from collections.abc import Callable

import httpx

from app import config


class ModelOutputCutError(RuntimeError):
    """Model bị cắt vì chạm max_tokens — dấu hiệu lặp vô tận, không dùng câu trả lời dở."""


async def ask_local_model(
    messages: list[dict],
    *,
    temperature: float,
    max_tokens: int,
    json_schema: dict | None = None,
) -> tuple[str, dict]:
    """Gọi llama-server một lần. Luôn gửi rõ thông số lấy mẫu, không dựa vào mặc định của server."""
    body = request_body(messages, temperature, max_tokens, json_schema)

    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=config.LLM_BASE_URL, timeout=config.LLM_TIMEOUT_SECONDS) as client:
        response = await client.post("/chat/completions", json=body)
        response.raise_for_status()
    result = response.json()
    duration_ms = round((time.perf_counter() - started) * 1000)

    choice = result["choices"][0]
    if choice.get("finish_reason") == "length":
        raise ModelOutputCutError(f"model chạm max_tokens={max_tokens}")
    usage = {
        "model": config.LLM_MODEL,
        "input_tokens": result["usage"]["prompt_tokens"],
        "output_tokens": result["usage"]["completion_tokens"],
        "duration_ms": duration_ms,
    }
    return choice["message"]["content"], usage


def request_body(messages: list[dict], temperature: float, max_tokens: int, json_schema: dict | None) -> dict:
    body = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": config.LLM_TOP_P,
        "top_k": config.LLM_TOP_K,
        "seed": config.LLM_SEED,
        "presence_penalty": 0,
        "max_tokens": max_tokens,
    }
    if json_schema is not None:
        # Ép đầu ra theo schema (grammar của llama.cpp) — README tools/server, mục response_format.
        body["response_format"] = {"type": "json_object", "schema": json_schema}
    return body


async def stream_local_model_json(messages: list[dict], json_schema: dict, *, temperature: float, max_tokens: int,
                                  on_text: Callable[[str], None]) -> tuple[dict, dict]:
    """Như ask_local_model_for_json nhưng nhận chữ dần (server-sent events) — on_text(chữ đã nhận tới lúc này) sau mỗi
    mẩu, để hiện câu trả lời đang viết. Định dạng của llama-server b11796: mỗi dòng "data: {…}" có
    choices[0].delta.content; finish_reason ở mẩu cuối có choices; stream_options.include_usage → thêm một mẩu "usage";
    kết thúc bằng "data: [DONE]". Stream chạy được cùng response_format có schema."""
    body = {**request_body(messages, temperature, max_tokens, json_schema),
            "stream": True, "stream_options": {"include_usage": True}}
    pieces, usage, finish_reason = [], None, None
    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=config.LLM_BASE_URL, timeout=config.LLM_TIMEOUT_SECONDS) as client:
        async with client.stream("POST", "/chat/completions", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line.removeprefix("data: "))
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    finish_reason = choice.get("finish_reason") or finish_reason
                    if piece := (choice.get("delta") or {}).get("content"):
                        pieces.append(piece)
                        on_text("".join(pieces))
    if finish_reason == "length":
        raise ModelOutputCutError(f"model chạm max_tokens={max_tokens}")
    return json.loads("".join(pieces)), {
        "model": config.LLM_MODEL,
        "input_tokens": (usage or {}).get("prompt_tokens", 0),
        "output_tokens": (usage or {}).get("completion_tokens", 0),
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }


async def ask_local_model_for_json(messages: list[dict], json_schema: dict, *, temperature: float,
                                   max_tokens: int) -> tuple[dict, dict]:
    """Như ask_local_model nhưng ép JSON theo schema và trả về dict đã parse."""
    content, usage = await ask_local_model(
        messages, temperature=temperature, max_tokens=max_tokens, json_schema=json_schema
    )
    return json.loads(content), usage


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Vector BGE-M3 (đã chuẩn hoá L2 — README llama-server, /v1/embeddings) từ llama-server thứ hai, cổng 9932."""
    async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{config.EMBEDDING_BASE_URL}/embeddings",
                                     json={"model": config.EMBEDDING_MODEL, "input": texts})
        response.raise_for_status()
    data = sorted(response.json()["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in data]

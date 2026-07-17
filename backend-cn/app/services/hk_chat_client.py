"""调用香港网关的 Codex 会话接口。

- create_session: 为用户新建 codex 会话，返回 thread_id
- stream_message: 流式发送消息，异步产出 SSE 事件字典（透传香港 SSE）
- delete_session: 归档会话 + 删除工作区
"""

import json
import time
from typing import AsyncIterator

import httpx

from app.config import settings
from app.logger import get_logger

logger = get_logger("hk_chat")

_SSE_TIMEOUT = None  # 流式请求不设整体超时，靠 httpx 连接/读取超时


class HKChatError(Exception):
    """香港聊天服务调用失败。"""


def _headers() -> dict:
    return {"X-Internal-Secret": settings.hk_internal_secret}


async def create_session(user_id: str) -> str:
    url = f"{settings.hk_base_url}/internal/chat/sessions"
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.hk_timeout_seconds) as client:
            resp = await client.post(url, headers=_headers(), data={"user_id": user_id})
    except httpx.RequestError as exc:
        logger.error("无法连接香港创建会话: user_id=%s 错误=%s", user_id, exc)
        raise HKChatError(f"无法连接会话服务: {exc}") from exc

    if resp.status_code != 200:
        detail = resp.text[:300] if resp.text else "未知错误"
        logger.error("香港创建会话返回错误: status=%s detail=%s 耗时=%.2fs",
                     resp.status_code, detail, time.monotonic() - started)
        raise HKChatError(f"会话服务返回错误: {resp.status_code}")

    thread_id = resp.json().get("thread_id")
    if not thread_id:
        raise HKChatError("会话服务未返回 thread_id")
    logger.info("香港会话已创建: user_id=%s thread_id=%s 耗时=%.2fs",
                user_id, thread_id, time.monotonic() - started)
    return thread_id


async def delete_session(user_id: str, thread_id: str) -> None:
    url = f"{settings.hk_base_url}/internal/chat/sessions/{thread_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(url, headers=_headers(), data={"user_id": user_id})
        if resp.status_code not in (200, 204):
            logger.warning("香港删除会话返回非200: status=%s thread_id=%s", resp.status_code, thread_id)
    except httpx.RequestError as exc:
        logger.warning("无法连接香港删除会话: thread_id=%s 错误=%s", thread_id, exc)


async def stream_message(
    thread_id: str,
    user_id: str,
    text: str,
    images: list[tuple[bytes, str]],
) -> AsyncIterator[dict]:
    """流式发送消息，异步产出事件字典。

    事件：{"type":"delta","text":...} / {"type":"done","text":...,"usage":{...}}
          / {"type":"error","detail":...}
    """
    url = f"{settings.hk_base_url}/internal/chat/sessions/{thread_id}/messages"
    data = {"user_id": user_id, "text": text}
    files = [("images", (fn, img)) for img, fn in images]

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_SSE_TIMEOUT) as client:
            async with client.stream(
                "POST", url, headers=_headers(), data=data, files=files
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    detail = body.decode(errors="replace")[:300] if body else "未知错误"
                    logger.error("香港流式消息返回错误: status=%s detail=%s 耗时=%.2fs",
                                 resp.status_code, detail, time.monotonic() - started)
                    yield {"type": "error", "detail": f"会话服务返回错误: {resp.status_code}"}
                    return
                # 解析 SSE：event 行决定类型，data 行携带 JSON 负载
                current_event = ""
                async for line in resp.aiter_lines():
                    if not line:
                        current_event = ""
                        continue
                    if line.startswith("event: "):
                        current_event = line[len("event: "):].strip()
                        continue
                    if line.startswith("data: "):
                        payload = line[len("data: "):]
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        obj["type"] = current_event or "delta"
                        yield obj
                        current_event = ""
    except httpx.RequestError as exc:
        logger.error("香港流式消息连接失败: thread_id=%s 错误=%s 耗时=%.2fs",
                     thread_id, exc, time.monotonic() - started)
        yield {"type": "error", "detail": f"无法连接会话服务: {exc}"}

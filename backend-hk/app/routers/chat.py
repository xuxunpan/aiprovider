"""Codex 会话路由：内部接口（需 X-Internal-Secret）。

- POST /internal/chat/sessions            为用户创建新会话，返回 thread_id
- POST /internal/chat/sessions/{tid}/messages  发送消息（文本+可选多图），SSE 流式返回
- DELETE /internal/chat/sessions/{tid}    归档会话 + 删除工作区
"""

import json
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.logger import get_logger
from app.services import codex_service, workspace

router = APIRouter(prefix="/internal/chat", tags=["chat"])

logger = get_logger("chat")

_VALID_EXTS = {"png", "jpg", "jpeg", "webp"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _infer_ext(filename: str | None) -> str:
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _VALID_EXTS:
            return ext
    return "png"


@router.post("/sessions")
async def create_session(user_id: str = Form(...)):
    try:
        thread_id = await codex_service.start_thread(user_id)
    except codex_service.CodexServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"thread_id": thread_id}


@router.post("/sessions/{thread_id}/messages")
async def send_message(
    thread_id: str,
    user_id: str = Form(...),
    text: str = Form(...),
    images: List[UploadFile] = File(default=[]),
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    image_paths: list[str] = []
    for img in images:
        img_bytes = await img.read()
        if not img_bytes:
            continue
        ext = _infer_ext(img.filename)
        path = workspace.save_upload(user_id, img_bytes, ext)
        image_paths.append(path)

    logger.info(
        "收到聊天消息: thread_id=%s user_id=%s text_len=%s image_count=%s",
        thread_id, user_id, len(text), len(image_paths),
    )

    async def event_stream():
        try:
            async for evt in codex_service.stream_turn(
                thread_id, user_id, text, image_paths
            ):
                etype = evt.get("type")
                if etype == "delta":
                    yield _sse("delta", {"text": evt.get("text", "")})
                elif etype == "done":
                    yield _sse("done", {"text": evt.get("text", ""), "usage": evt.get("usage", {})})
                elif etype == "error":
                    yield _sse("error", {"detail": evt.get("detail", "未知错误")})
        except Exception as exc:
            logger.error("聊天流式响应异常: thread_id=%s 错误=%s", thread_id, exc)
            yield _sse("error", {"detail": f"服务器异常: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/sessions/{thread_id}")
async def delete_session(thread_id: str, user_id: str = Form(...)):
    await codex_service.archive_thread(thread_id)
    workspace.delete_workspace(user_id)
    logger.info("已删除会话及工作区: thread_id=%s user_id=%s", thread_id, user_id)
    return {"ok": True}

"""聊天会话路由（前缀 /api/chat，需 JWT 鉴权）。

- GET    /api/chat/sessions                    会话列表
- POST   /api/chat/sessions                    新建会话（调香港 thread_start）
- GET    /api/chat/sessions/{id}               会话详情 + 历史消息
- DELETE /api/chat/sessions/{id}               删除会话（落库 + 香港归档）
- POST   /api/chat/sessions/{id}/messages      发送消息（预扣积分 + SSE 流式）
- GET    /api/chat/sessions/{id}/files/{name}  会话图片文件（鉴权+归属）
"""

import json
from datetime import datetime, timezone
from typing import List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger
from app.schemas.chat import (
    ChatImageOut,
    ChatMessageOut,
    ChatSessionCreated,
    ChatSessionListItem,
    ChatSessionListOut,
    ChatSessionOut,
)
from app.services import chat_service, hk_chat_client, image_utils, storage
from app.services import credit_service as cs

router = APIRouter(prefix="/api/chat", tags=["chat"])

logger = get_logger("chat_router")

_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}


def _ext_from_content_type(ct: str | None) -> str:
    if ct and "/" in ct:
        ext = ct.rsplit("/", 1)[-1].lower()
        if ext in _ALLOWED_EXTS:
            return ext
    return "png"


def _message_out(doc: dict) -> ChatMessageOut:
    return ChatMessageOut(
        id=str(doc["_id"]),
        role=doc["role"],
        content=doc.get("content", ""),
        images=[ChatImageOut(path=im["path"], filename=im.get("filename", im["path"])) for im in doc.get("images", [])],
        status=doc.get("status", "success"),
        error_msg=doc.get("error_msg"),
        usage=doc.get("usage", {}),
        created_at=doc["created_at"],
    )


async def _load_session_or_404(db, session_id: str, user_id: ObjectId) -> dict:
    try:
        sid = ObjectId(session_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="会话不存在")
    sess = await chat_service.get_session(db, sid, user_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return sess


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _is_rollout_missing(detail: str) -> bool:
    """判断是否为 Codex 会话 rollout 丢失导致的可重建错误。"""
    return "no rollout found" in detail.lower()


# ── 会话 CRUD ──────────────────────────────────────────────

@router.get("/sessions", response_model=ChatSessionListOut)
async def list_sessions(user: dict = Depends(get_current_user)):
    db = get_db()
    docs = await chat_service.list_sessions(db, user["_id"])
    items = [
        ChatSessionListItem(
            id=str(d["_id"]),
            title=d.get("title", "新会话"),
            last_message_at=d.get("last_message_at"),
            created_at=d["created_at"],
        )
        for d in docs
    ]
    return ChatSessionListOut(sessions=items)


@router.post("/sessions", status_code=201, response_model=ChatSessionCreated)
async def create_session(user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        thread_id = await hk_chat_client.create_session(str(user["_id"]))
    except hk_chat_client.HKChatError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    sid = await chat_service.create_session(db, user["_id"], thread_id)
    return ChatSessionCreated(session_id=str(sid))


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
async def get_session_detail(session_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    sess = await _load_session_or_404(db, session_id, user["_id"])
    messages = await chat_service.list_messages(db, sess["_id"])
    return ChatSessionOut(
        id=str(sess["_id"]),
        title=sess.get("title", "新会话"),
        created_at=sess["created_at"],
        last_message_at=sess.get("last_message_at"),
        messages=[_message_out(m) for m in messages],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    sess = await _load_session_or_404(db, session_id, user["_id"])
    await hk_chat_client.delete_session(str(user["_id"]), sess["hk_thread_id"])
    storage.delete_chat_dir(str(sess["_id"]))
    await chat_service.delete_session(db, sess["_id"], user["_id"])
    return {"ok": True}


# ── 发送消息（SSE 流式） ──────────────────────────────────────

@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    text: str = Form(""),
    images: List[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
):
    text = text.strip()
    if not text and not images:
        raise HTTPException(status_code=400, detail="请输入消息内容或上传图片")
    if len(images) > settings.max_chat_images:
        raise HTTPException(
            status_code=400,
            detail=f"单条消息最多上传 {settings.max_chat_images} 张图片",
        )

    db = get_db()
    sess = await _load_session_or_404(db, session_id, user["_id"])

    # 会话级并发锁：同一会话同一时刻仅一轮对话
    lock = await chat_service.get_session_lock(session_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="上一条消息还在生成中，请稍候")

    # 预扣积分
    cost = settings.cost_per_chat
    if cost > 0:
        reserved = await cs.try_reserve_credits(db, user["_id"], cost)
        if not reserved:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="积分已用完，请充值后继续使用",
            )

    # 处理上传图片：CN 落盘存档 + 缩放
    image_records: list[dict] = []
    hk_images: list[tuple[bytes, str]] = []
    for img in images:
        if img.content_type not in _ALLOWED_TYPES:
            if cost > 0:
                await cs.refund_credits(db, user["_id"], cost)
            raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、WEBP 格式的图片")
        img_bytes = await img.read()
        if not img_bytes:
            continue
        if len(img_bytes) > settings.max_upload_bytes:
            if cost > 0:
                await cs.refund_credits(db, user["_id"], cost)
            raise HTTPException(status_code=400, detail=f"图片大小不能超过 {settings.max_upload_mb}MB")
        img_bytes = image_utils.resize_if_needed(img_bytes, settings.max_image_dimension)
        ext = _ext_from_content_type(img.content_type)
        rel = storage.save_chat_image(str(sess["_id"]), img_bytes, ext)
        image_records.append({"path": rel, "filename": img.filename or rel})
        hk_images.append((img_bytes, img.filename or f"upload.{ext}"))

    # 存用户消息
    await chat_service.add_user_message(db, sess["_id"], user["_id"], text, image_records)

    thread_id = sess["hk_thread_id"]
    uid = str(user["_id"])
    sid_obj = sess["_id"]

    async def event_stream():
        async with lock:
            delta_parts: list[str] = []
            final_text = ""
            usage: dict = {}
            errored = False
            error_detail = ""
            current_thread_id = thread_id
            retried = False
            try:
                for _attempt in range(2):
                    attempt_rebuild = False
                    async for evt in hk_chat_client.stream_message(
                        current_thread_id, uid, text, hk_images
                    ):
                        etype = evt.get("type")
                        if etype == "delta":
                            delta_parts.append(evt.get("text", ""))
                            yield _sse("delta", {"text": evt.get("text", "")})
                        elif etype == "done":
                            final_text = evt.get("text", "")
                            usage = evt.get("usage", {})
                            yield _sse("done", {"text": final_text, "usage": usage})
                        elif etype == "error":
                            detail = evt.get("detail", "未知错误")
                            if not retried and _is_rollout_missing(detail):
                                # Codex rollout 丢失：重建会话后重试一次
                                retried = True
                                attempt_rebuild = True
                                logger.warning(
                                    "会话 rollout 丢失，自动重建: session_id=%s old_thread=%s",
                                    session_id, current_thread_id,
                                )
                                try:
                                    new_thread_id = await hk_chat_client.create_session(uid)
                                    await chat_service.update_session_thread(
                                        db, sid_obj, new_thread_id
                                    )
                                    current_thread_id = new_thread_id
                                    logger.info(
                                        "会话已重建，即将重试: session_id=%s new_thread=%s",
                                        session_id, current_thread_id,
                                    )
                                    delta_parts.clear()
                                    final_text = ""
                                    usage = {}
                                except Exception as rebuild_exc:
                                    logger.error(
                                        "重建会话失败，回退为错误: session_id=%s 错误=%s",
                                        session_id, rebuild_exc,
                                    )
                                    attempt_rebuild = False
                                    errored = True
                                    error_detail = "会话状态已失效且重建失败，请新建会话"
                                    yield _sse("error", {"detail": error_detail})
                            else:
                                errored = True
                                error_detail = detail
                                yield _sse("error", {"detail": detail})
                            break
                    if not attempt_rebuild:
                        break
            except Exception as exc:
                logger.exception("流式消息异常: session_id=%s", session_id)
                errored = True
                error_detail = f"服务器异常: {exc}"
                yield _sse("error", {"detail": error_detail})

            # 若未收到 done（异常中断），用已累积的 delta 兜底
            if not final_text:
                final_text = "".join(delta_parts).strip()

            # 落库助手消息 + 积分处理
            if errored:
                await chat_service.add_assistant_message(
                    db, sid_obj, user["_id"], final_text, "failed", error_detail, {}
                )
                if cost > 0:
                    await cs.refund_credits(db, user["_id"], cost)
            else:
                await chat_service.add_assistant_message(
                    db, sid_obj, user["_id"], final_text, "success", None, usage
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 会话图片文件服务 ──────────────────────────────────────────

@router.get("/sessions/{session_id}/files/{filename}")
async def serve_chat_file(
    session_id: str,
    filename: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    sess = await _load_session_or_404(db, session_id, user["_id"])
    safe_sid = "".join(c for c in str(sess["_id"]) if c.isalnum())
    # filename 形如 {uuid}.{ext}，但用户消息里存的 path 是 chat/{sid}/{file}
    # 直接用 safe_sid/filename 拼相对路径并校验归属
    safe_name = "".join(c for c in filename if c.isalnum() or c == ".")
    rel_path = f"chat/{safe_sid}/{safe_name}"
    full = storage.resolve_chat_path(rel_path)
    if full is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "png"
    media_type = f"image/{ext}" if ext in _ALLOWED_EXTS else "image/png"
    return FileResponse(
        full,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )

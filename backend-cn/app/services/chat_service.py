"""聊天会话/消息持久化 + 积分预扣退还 + 会话级并发锁。"""

import asyncio
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.logger import get_logger

logger = get_logger("chat")

# 会话级并发锁：同一会话同一时刻只允许一轮对话进行，避免 codex 同会话并发冲突。
_session_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def get_session_lock(session_id: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[session_id] = lock
        return lock


def _release_session_lock(session_id: str) -> None:
    # 保留锁对象以便复用；长期未用的清理可选，此处简化处理。
    pass


async def create_session(
    db: AsyncIOMotorDatabase, user_id: ObjectId, hk_thread_id: str
) -> ObjectId:
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "hk_thread_id": hk_thread_id,
        "title": "新会话",
        "created_at": now,
        "updated_at": now,
        "last_message_at": None,
    }
    result = await db.chat_sessions.insert_one(doc)
    logger.info("聊天会话已创建: session_id=%s user_id=%s", result.inserted_id, user_id)
    return result.inserted_id


async def get_session(db: AsyncIOMotorDatabase, session_id: ObjectId, user_id: ObjectId) -> dict | None:
    sess = await db.chat_sessions.find_one({"_id": session_id})
    if not sess or sess["user_id"] != user_id:
        return None
    return sess


async def update_session_thread(
    db: AsyncIOMotorDatabase, session_id: ObjectId, hk_thread_id: str
) -> None:
    """更新会话的 hk_thread_id（Codex rollout 丢失后自动重建会话时调用）。"""
    now = datetime.now(timezone.utc)
    await db.chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"hk_thread_id": hk_thread_id, "updated_at": now}},
    )
    logger.info(
        "会话 hk_thread_id 已更新: session_id=%s new_thread_id=%s",
        session_id, hk_thread_id,
    )


async def list_sessions(db: AsyncIOMotorDatabase, user_id: ObjectId) -> list[dict]:
    cursor = db.chat_sessions.find({"user_id": user_id}).sort("last_message_at", -1)
    return [doc async for doc in cursor]


async def delete_session(db: AsyncIOMotorDatabase, session_id: ObjectId, user_id: ObjectId) -> dict | None:
    sess = await get_session(db, session_id, user_id)
    if sess is None:
        return None
    await db.chat_messages.delete_many({"session_id": session_id})
    await db.chat_sessions.delete_one({"_id": session_id})
    logger.info("聊天会话已删除: session_id=%s", session_id)
    return sess


async def add_user_message(
    db: AsyncIOMotorDatabase,
    session_id: ObjectId,
    user_id: ObjectId,
    content: str,
    images: list[dict],
) -> ObjectId:
    now = datetime.now(timezone.utc)
    doc = {
        "session_id": session_id,
        "user_id": user_id,
        "role": "user",
        "content": content,
        "images": images,
        "status": "success",
        "error_msg": None,
        "usage": {},
        "created_at": now,
    }
    result = await db.chat_messages.insert_one(doc)
    await db.chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_message_at": now, "updated_at": now}},
    )
    return result.inserted_id


async def add_assistant_message(
    db: AsyncIOMotorDatabase,
    session_id: ObjectId,
    user_id: ObjectId,
    content: str,
    status: str,
    error_msg: str | None = None,
    usage: dict | None = None,
) -> ObjectId:
    now = datetime.now(timezone.utc)
    doc = {
        "session_id": session_id,
        "user_id": user_id,
        "role": "assistant",
        "content": content,
        "images": [],
        "status": status,
        "error_msg": error_msg,
        "usage": usage or {},
        "created_at": now,
    }
    result = await db.chat_messages.insert_one(doc)
    await db.chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_message_at": now, "updated_at": now}},
    )
    # 首条助手消息后用内容前缀更新会话标题
    if status == "success" and content:
        title = content.strip().replace("\n", " ")[:24]
        if title:
            await db.chat_sessions.update_one(
                {"_id": session_id, "title": "新会话"},
                {"$set": {"title": title}},
            )
    return result.inserted_id


async def list_messages(db: AsyncIOMotorDatabase, session_id: ObjectId) -> list[dict]:
    cursor = db.chat_messages.find({"session_id": session_id}).sort("created_at", 1)
    return [doc async for doc in cursor]

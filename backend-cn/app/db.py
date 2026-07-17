from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.logger import get_logger

logger = get_logger("db")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("数据库尚未初始化")
    return _db


async def connect_db() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.mongo_uri)
    _db = _client[settings.mongo_db]
    await _ensure_indexes(_db)
    logger.info("MongoDB 连接成功: db=%s", settings.mongo_db)


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB 连接已关闭")


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("email", unique=True)
    await db.products.create_index("user_id")
    await db.targets.create_index("product_id")
    await db.targets.create_index("user_id")
    await db.targets.create_index([("status", 1), ("created_at", 1)])
    await db.recharge_records.create_index("user_id")
    await db.recharge_records.create_index("out_trade_no", unique=True, sparse=True)
    # 聊天会话/消息
    await db.chat_sessions.create_index("user_id")
    await db.chat_sessions.create_index([("user_id", 1), ("last_message_at", -1)])
    await db.chat_messages.create_index("session_id")
    await db.chat_messages.create_index("user_id")

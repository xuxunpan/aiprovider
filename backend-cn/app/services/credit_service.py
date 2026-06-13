from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.logger import get_logger

logger = get_logger("credit")


async def try_reserve_credits(db: AsyncIOMotorDatabase, user_id: ObjectId, cost: int) -> bool:
    """原子预扣积分。余额不足返回 False，不做任何修改。"""
    result = await db.users.find_one_and_update(
        {"_id": user_id, "credits": {"$gte": cost}},
        {"$inc": {"credits": -cost}},
    )
    ok = result is not None
    if ok:
        logger.info("预扣积分成功: user_id=%s cost=%s", user_id, cost)
    else:
        logger.warning("预扣积分失败(余额不足): user_id=%s cost=%s", user_id, cost)
    return ok


async def refund_credits(db: AsyncIOMotorDatabase, user_id: ObjectId, cost: int) -> None:
    """退还此前预扣的积分。"""
    await db.users.update_one({"_id": user_id}, {"$inc": {"credits": cost}})
    logger.info("退还积分: user_id=%s cost=%s", user_id, cost)


async def get_credits(db: AsyncIOMotorDatabase, user_id: ObjectId) -> int:
    user = await db.users.find_one({"_id": user_id}, {"credits": 1})
    return int(user.get("credits", 0)) if user else 0


# --- Targets (新数据模型) ---

async def create_target(
    db: AsyncIOMotorDatabase, product_id: ObjectId, user_id: ObjectId, prompt: str, cost: int
) -> ObjectId:
    doc = {
        "product_id": product_id,
        "user_id": user_id,
        "prompt": prompt,
        "status": "queued",
        "cost": cost,
        "cn_image_path": None,
        "error_msg": None,
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "finished_at": None,
    }
    result = await db.targets.insert_one(doc)
    logger.info("目标图已创建: target_id=%s product_id=%s", result.inserted_id, product_id)
    return result.inserted_id


async def claim_next_queued_target(
    db: AsyncIOMotorDatabase, user_id: ObjectId, max_concurrent: int
) -> dict | None:
    """原子认领一个排队任务。

    先通过 find_one_and_update 原子地将最早排队任务标记为 generating，
    然后核验并发数是否超限——若超限立即回退为 queued。
    在单进程调度下不会触发回退；多 worker 部署时起到安全兜底作用。
    """
    result = await db.targets.find_one_and_update(
        {"user_id": user_id, "status": "queued"},
        {
            "$set": {
                "status": "generating",
                "started_at": datetime.now(timezone.utc),
            }
        },
        sort=[("created_at", 1)],
    )
    if not result:
        return None

    generating_count = await db.targets.count_documents(
        {"user_id": user_id, "status": "generating"}
    )
    if generating_count > max_concurrent:
        await db.targets.update_one(
            {"_id": result["_id"]},
            {"$set": {"status": "queued", "started_at": None}},
        )
        logger.warning(
            "并发上限触发回退: user_id=%s target_id=%s count=%s",
            user_id, result["_id"], generating_count,
        )
        return None

    logger.info("任务已认领: target_id=%s user_id=%s", result["_id"], user_id)
    return result


async def mark_target_success(
    db: AsyncIOMotorDatabase, target_id: ObjectId, cn_image_path: str
) -> None:
    await db.targets.update_one(
        {"_id": target_id},
        {
            "$set": {
                "status": "success",
                "cn_image_path": cn_image_path,
                "finished_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info("目标图生成成功: target_id=%s", target_id)


async def mark_target_failed(
    db: AsyncIOMotorDatabase, target_id: ObjectId, error_msg: str
) -> None:
    await db.targets.update_one(
        {"_id": target_id},
        {
            "$set": {
                "status": "failed",
                "error_msg": error_msg,
                "finished_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info("目标图生成失败: target_id=%s error=%s", target_id, error_msg)


async def reset_stale_generating(db: AsyncIOMotorDatabase) -> int:
    """启动时把残留的 generating 重置为 queued。"""
    result = await db.targets.update_many(
        {"status": "generating"},
        {"$set": {"status": "queued", "started_at": None}},
    )
    logger.info("重置残留 generating 任务: count=%s", result.modified_count)
    return result.modified_count


async def count_user_concurrent(db: AsyncIOMotorDatabase, user_id: ObjectId) -> int:
    return await db.targets.count_documents({"user_id": user_id, "status": "generating"})


async def count_user_queued(db: AsyncIOMotorDatabase, user_id: ObjectId) -> int:
    return await db.targets.count_documents({"user_id": user_id, "status": "queued"})

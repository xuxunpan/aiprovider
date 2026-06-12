from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def try_reserve_credits(db: AsyncIOMotorDatabase, user_id: ObjectId, cost: int) -> bool:
    """原子预扣积分。余额不足返回 False，不做任何修改。"""
    result = await db.users.find_one_and_update(
        {"_id": user_id, "credits": {"$gte": cost}},
        {"$inc": {"credits": -cost}},
    )
    return result is not None


async def refund_credits(db: AsyncIOMotorDatabase, user_id: ObjectId, cost: int) -> None:
    """退还此前预扣的积分。"""
    await db.users.update_one({"_id": user_id}, {"$inc": {"credits": cost}})


async def get_credits(db: AsyncIOMotorDatabase, user_id: ObjectId) -> int:
    user = await db.users.find_one({"_id": user_id}, {"credits": 1})
    return int(user.get("credits", 0)) if user else 0


async def create_task(
    db: AsyncIOMotorDatabase, user_id: ObjectId, prompt: str, cost: int
) -> ObjectId:
    doc = {
        "user_id": user_id,
        "prompt": prompt,
        "status": "pending",
        "cost": cost,
        "hk_image_path": None,
        "error_msg": None,
        "created_at": datetime.now(timezone.utc),
        "finished_at": None,
    }
    result = await db.tasks.insert_one(doc)
    return result.inserted_id


async def mark_task_success(
    db: AsyncIOMotorDatabase, task_id: ObjectId, hk_image_path: str
) -> None:
    await db.tasks.update_one(
        {"_id": task_id},
        {
            "$set": {
                "status": "success",
                "hk_image_path": hk_image_path,
                "finished_at": datetime.now(timezone.utc),
            }
        },
    )


async def mark_task_failed(db: AsyncIOMotorDatabase, task_id: ObjectId, error_msg: str) -> None:
    await db.tasks.update_one(
        {"_id": task_id},
        {
            "$set": {
                "status": "failed",
                "error_msg": error_msg,
                "finished_at": datetime.now(timezone.utc),
            }
        },
    )

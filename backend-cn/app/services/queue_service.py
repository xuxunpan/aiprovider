import asyncio
import traceback

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.db import get_db
from app.logger import get_logger
from app.services import credit_service as cs
from app.services import hk_client, storage

logger = get_logger("queue")


async def _execute_target(target_id: ObjectId, product_id: ObjectId, user_id: ObjectId) -> None:
    """执行单个目标图生成任务。"""
    db = get_db()
    cost = settings.cost_per_image
    try:
        ref_images = storage.get_ref_images(str(product_id))
        if not ref_images:
            logger.warning("产品无参考图, 标记失败: target_id=%s", target_id)
            await cs.mark_target_failed(db, target_id, "产品缺少参考图")
            await cs.refund_credits(db, user_id, cost)
            return

        target = await db.targets.find_one({"_id": target_id})
        prompt = target["prompt"] if target else ""
        cost = target["cost"] if target else cost

        result_bytes = await hk_client.generate_image(
            product_id=str(product_id),
            prompt=prompt,
            ref_images=ref_images,
        )
    except hk_client.HKServiceError as exc:
        await cs.mark_target_failed(db, target_id, str(exc))
        await cs.refund_credits(db, user_id, cost)
        logger.warning("目标图生成失败已退还积分: target_id=%s", target_id)
        return
    except Exception:
        await cs.mark_target_failed(db, target_id, "生成过程发生未知错误")
        await cs.refund_credits(db, user_id, cost)
        logger.exception("目标图生成未知错误已退还积分: target_id=%s", target_id)
        return

    image_path = storage.save_target_image(str(product_id), str(target_id), result_bytes)
    await cs.mark_target_success(db, target_id, image_path)
    logger.info("目标图生成完成: target_id=%s path=%s", target_id, image_path)


async def _process_queue(db: AsyncIOMotorDatabase) -> None:
    """扫描所有用户，为有空闲槽的用户认领排队任务。"""
    pipeline = [
        {"$match": {"status": "queued"}},
        {"$group": {"_id": "$user_id"}},
    ]
    users_with_queued = []
    async for doc in db.targets.aggregate(pipeline):
        users_with_queued.append(doc["_id"])

    max_con = settings.max_concurrent_generations
    for user_id in users_with_queued:
        while True:
            claimed = await cs.claim_next_queued_target(db, user_id, max_con)
            if claimed is None:
                break
            asyncio.create_task(
                _execute_target(claimed["_id"], claimed["product_id"], claimed["user_id"])
            )


async def dispatcher_loop() -> None:
    """主调度循环：定期扫描 MongoDB，认领排队任务并派生执行。"""
    logger.info("任务调度器已启动, 最大并发=%s", settings.max_concurrent_generations)
    db = get_db()

    # 启动恢复：把残留 generating 重置
    await cs.reset_stale_generating(db)

    while True:
        try:
            await _process_queue(db)
        except Exception:
            logger.exception("调度器循环异常: %s", traceback.format_exc())
        await asyncio.sleep(2)

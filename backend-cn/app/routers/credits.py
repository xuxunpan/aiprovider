from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger
from app.schemas.recharge import RechargeRecordsOut, RechargeRecordOut

router = APIRouter(prefix="/api/credits", tags=["credits"])

logger = get_logger("credits")


@router.get("")
async def get_credits(user: dict = Depends(get_current_user)):
    return {"credits": user.get("credits", 0)}


@router.get("/records", response_model=RechargeRecordsOut)
async def get_recharge_records(user: dict = Depends(get_current_user)):
    db = get_db()
    cursor = db.recharge_records.find({"user_id": user["_id"]}).sort("created_at", -1)
    records = []
    async for doc in cursor:
        records.append(RechargeRecordOut(
            id=str(doc["_id"]),
            amount_credits=doc.get("amount_credits", doc.get("amount", 0)),
            price=doc.get("price", 0),
            status=doc.get("status", "pending"),
            created_at=doc["created_at"],
        ))
    return RechargeRecordsOut(records=records)


@router.post("/recharge")
async def recharge(user: dict = Depends(get_current_user)):
    # 占位接口：充值功能尚未上线
    logger.info("用户尝试充值(功能未上线): user_id=%s", user["_id"])
    return {
        "ok": False,
        "message": "充值功能即将上线，敬请期待。如需更多积分请联系客服。",
    }


@router.post("/recharge/record")
async def create_recharge_record(
    amount: int,
    price: float,
    user: dict = Depends(get_current_user),
):
    """写入充值记录（占位状态 pending）。"""
    db = get_db()
    doc = {
        "user_id": user["_id"],
        "amount_credits": amount,
        "price": price,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.recharge_records.insert_one(doc)
    logger.info("充值记录已创建: user_id=%s amount=%s price=%s", user["_id"], amount, price)
    return {"ok": True, "record_id": str(result.inserted_id)}

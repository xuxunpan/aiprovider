from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger
from app.schemas.recharge import (
    CreateRechargeRecordOut,
    CreateRechargeRecordRequest,
    RechargePackageOut,
    RechargePackagesOut,
    RechargeRecordOut,
    RechargeRecordsOut,
)

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


@router.get("/recharge/packages", response_model=RechargePackagesOut)
async def get_recharge_packages():
    """返回后端权威套餐列表，前端据此渲染充值选项。"""
    packages = [
        RechargePackageOut(id=p["id"], credits=p["credits"], price=p["price"])
        for p in settings.recharge_package_list
    ]
    return RechargePackagesOut(packages=packages)


@router.post("/recharge/record", response_model=CreateRechargeRecordOut)
async def create_recharge_record(
    body: CreateRechargeRecordRequest,
    user: dict = Depends(get_current_user),
):
    """写入充值记录——仅接受 package_id，金额/积分为后端权威校验。"""
    pkg = settings.recharge_package_map.get(body.package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail="无效的充值套餐")
    db = get_db()
    doc = {
        "user_id": user["_id"],
        "amount_credits": pkg["credits"],
        "price": pkg["price"],
        "package_id": body.package_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.recharge_records.insert_one(doc)
    logger.info("充值记录已创建: user_id=%s package=%s credits=%s price=%s",
                user["_id"], body.package_id, pkg["credits"], pkg["price"])
    return CreateRechargeRecordOut(ok=True, record_id=str(result.inserted_id))

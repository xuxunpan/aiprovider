from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request

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
    RechargeResponse,
    RechargeStatusOut,
)
from app.services import wechat_pay

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


@router.post("/recharge", response_model=RechargeResponse)
async def recharge(
    body: CreateRechargeRecordRequest,
    user: dict = Depends(get_current_user),
):
    pkg = settings.recharge_package_map.get(body.package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail="无效的充值套餐")

    db = get_db()

    out_trade_no, code_url = await wechat_pay.create_native_order(pkg, str(user["_id"]))

    doc = {
        "user_id": user["_id"],
        "amount_credits": pkg["credits"],
        "price": pkg["price"],
        "package_id": body.package_id,
        "status": "pending",
        "out_trade_no": out_trade_no,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = await db.recharge_records.insert_one(doc)
    except Exception:
        logger.exception("写入充值记录失败: out_trade_no=%s", out_trade_no)
        raise HTTPException(status_code=500, detail="创建充值记录失败，请稍后重试")

    record_id = str(result.inserted_id)
    logger.info("充值记录已创建: user_id=%s package=%s credits=%s price=%s out_trade_no=%s",
                user["_id"], body.package_id, pkg["credits"], pkg["price"], out_trade_no)

    if code_url:
        return RechargeResponse(record_id=record_id, code_url=code_url)
    else:
        return RechargeResponse(
            record_id=record_id,
            message="充值功能即将上线，敬请期待。如需更多积分请联系客服。",
        )


@router.get("/recharge/packages", response_model=RechargePackagesOut)
async def get_recharge_packages():
    packages = [
        RechargePackageOut(id=p["id"], credits=p["credits"], price=p["price"])
        for p in settings.recharge_package_list
    ]
    return RechargePackagesOut(packages=packages)


@router.get("/recharge/{record_id}/status", response_model=RechargeStatusOut)
async def get_recharge_status(
    record_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    try:
        oid = ObjectId(record_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="无效的记录ID")

    doc = await db.recharge_records.find_one({"_id": oid, "user_id": user["_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="充值记录不存在")

    status = doc.get("status", "pending")
    amount_credits = doc.get("amount_credits", 0)

    if status == "pending":
        out_trade_no = doc.get("out_trade_no")
        if out_trade_no:
            wechat_result = await wechat_pay.query_order(out_trade_no)
            if wechat_result and wechat_result.get("trade_state") == "SUCCESS":
                await db.recharge_records.update_one(
                    {"_id": oid, "status": "pending"},
                    {"$set": {"status": "completed"}},
                )
                await db.users.update_one(
                    {"_id": doc["user_id"]},
                    {"$inc": {"credits": amount_credits}},
                )
                status = "completed"
                logger.info("轮询确认支付成功: record_id=%s credits=%s", record_id, amount_credits)

    return RechargeStatusOut(
        record_id=record_id,
        status=status,
        amount_credits=amount_credits,
        price=doc.get("price", 0),
    )


@router.post("/recharge/record", response_model=CreateRechargeRecordOut)
async def create_recharge_record(
    body: CreateRechargeRecordRequest,
    user: dict = Depends(get_current_user),
):
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



_notify_router = APIRouter(prefix="/api/credits", tags=["wechat-notify"])


@_notify_router.post("/recharge/wechat/notify")
async def wechat_pay_notify(request: Request):
    signature = request.headers.get("Wechatpay-Signature", "")
    serial_no = request.headers.get("Wechatpay-Serial", "")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    body_bytes = await request.body()

    logger.info("收到微信支付回调: serial=%s timestamp=%s", serial_no, timestamp)

    if not all([signature, serial_no, timestamp, nonce]):
        logger.warning("回调请求缺少必要签名头")
        return {"code": "FAIL", "message": "缺少签名头"}

    decrypted = await wechat_pay.verify_notify(signature, serial_no, timestamp, nonce, body_bytes)
    if not decrypted:
        return {"code": "FAIL", "message": "验签失败"}

    out_trade_no = decrypted.get("out_trade_no", "")
    trade_state = decrypted.get("trade_state", "")

    if trade_state != "SUCCESS":
        logger.info("支付回调非成功状态: out_trade_no=%s trade_state=%s", out_trade_no, trade_state)
        return {"code": "SUCCESS", "message": "已收到"}

    db = get_db()
    record = await db.recharge_records.find_one({"out_trade_no": out_trade_no})
    if not record:
        logger.error("回调订单号未匹配到充值记录: out_trade_no=%s", out_trade_no)
        return {"code": "FAIL", "message": "订单不存在"}

    if record.get("status") == "completed":
        logger.info("回调重复通知(已处理): out_trade_no=%s", out_trade_no)
        return {"code": "SUCCESS", "message": "已处理"}

    result = await db.recharge_records.update_one(
        {"_id": record["_id"], "status": "pending", "out_trade_no": out_trade_no},
        {"$set": {"status": "completed"}},
    )
    if result.modified_count == 0:
        logger.warning("回调更新记录状态失败(可能已被处理): out_trade_no=%s", out_trade_no)
        return {"code": "SUCCESS", "message": "已处理"}

    amount = record.get("amount_credits", 0)
    await db.users.update_one(
        {"_id": record["user_id"]},
        {"$inc": {"credits": amount}},
    )
    logger.info("支付回调处理完成: out_trade_no=%s user_id=%s credits=%s",
                out_trade_no, record["user_id"], amount)

    return {"code": "SUCCESS", "message": "成功"}


from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.logger import get_logger

router = APIRouter(prefix="/api/credits", tags=["credits"])

logger = get_logger("credits")


@router.get("")
async def get_credits(user: dict = Depends(get_current_user)):
    return {"credits": user.get("credits", 0)}


@router.post("/recharge")
async def recharge(user: dict = Depends(get_current_user)):
    # 占位接口：充值功能尚未上线
    logger.info("用户尝试充值(功能未上线): user_id=%s", user["_id"])
    return {
        "ok": False,
        "message": "充值功能即将上线，敬请期待。如需更多积分请联系客服。",
    }

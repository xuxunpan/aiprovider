from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger, mask_email
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.security import create_access_token, hash_password, is_admin, verify_password
from datetime import datetime, timezone

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = get_logger("auth")


@router.get("/registration-status")
async def registration_status():
    return {"enabled": settings.enable_registration}


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest):
    if not settings.enable_registration:
        raise HTTPException(status_code=403, detail="注册功能已关闭，如有疑问请联系管理员")
    db = get_db()
    email = payload.email.lower()
    user_doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "credits": settings.initial_credits,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await db.users.insert_one(user_doc)
    except DuplicateKeyError:
        logger.warning("注册失败(邮箱已存在): %s", mask_email(email))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录")

    logger.info(
        "用户注册成功: user_id=%s email=%s 初始积分=%s",
        result.inserted_id,
        mask_email(email),
        settings.initial_credits,
    )
    token = create_access_token(str(result.inserted_id))
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    db = get_db()
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if user is None or not user.get("password_hash") or not verify_password(payload.password, user["password_hash"]):
        logger.warning("登录失败(邮箱或密码错误): %s", mask_email(email))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    logger.info("用户登录成功: user_id=%s email=%s", user["_id"], mask_email(email))
    token = create_access_token(str(user["_id"]))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        credits=user.get("credits", 0),
        is_admin=is_admin(user.get("email")),
    )


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """普通用户修改自己的密码：需校验原密码。"""
    stored_hash = user.get("password_hash")
    if not stored_hash or not verify_password(payload.old_password, stored_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

    new_hash = hash_password(payload.new_password)
    await get_db().users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": new_hash}})
    logger.info("用户修改密码成功: user_id=%s email=%s", user["_id"], mask_email(user.get("email", "")))
    return {"ok": True}

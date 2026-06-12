from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger, mask_email
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = get_logger("auth")


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest):
    db = get_db()
    email = payload.email.lower()
    user_doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "credits": settings.initial_credits,
        "status": "active",
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
    return UserResponse(id=str(user["_id"]), email=user["email"], credits=user.get("credits", 0))

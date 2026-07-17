from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.logger import get_logger, mask_email
from app.schemas.auth import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateCreditsRequest,
    AdminUserItem,
    AdminUserListOut,
)
from app.security import hash_password, is_admin

router = APIRouter(prefix="/api/auth/admin", tags=["admin"])

logger = get_logger("admin")


def _to_item(doc: dict) -> AdminUserItem:
    created_at = doc.get("created_at")
    if created_at is None:
        try:
            created_at = doc["_id"].generation_time.astimezone(timezone.utc)
        except Exception:
            created_at = None
    return AdminUserItem(
        id=str(doc["_id"]),
        email=doc["email"],
        credits=int(doc.get("credits", 0)),
        status=doc.get("status", "active"),
        is_admin=is_admin(doc.get("email")),
        created_at=created_at,
    )


@router.get("/users", response_model=AdminUserListOut)
async def list_users(admin: dict = Depends(get_current_admin)):
    db = get_db()
    docs = await db.users.find({}, {"password_hash": 0}).sort("email", 1).to_list(length=None)
    return AdminUserListOut(users=[_to_item(d) for d in docs])


@router.post("/users", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED)
async def create_user(payload: AdminCreateUserRequest, admin: dict = Depends(get_current_admin)):
    db = get_db()
    email = payload.email.lower()
    user_doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "credits": payload.credits,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await db.users.insert_one(user_doc)
    except DuplicateKeyError:
        logger.warning("管理员创建用户失败(邮箱已存在): %s", mask_email(email))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已存在")

    doc = await db.users.find_one({"_id": result.inserted_id})
    logger.info(
        "管理员创建用户成功: admin=%s email=%s credits=%s",
        mask_email(admin.get("email", "")), mask_email(email), payload.credits,
    )
    return _to_item(doc)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(get_current_admin)):
    db = get_db()
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户 ID 非法")

    if oid == admin["_id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己")

    target = await db.users.find_one({"_id": oid})
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if is_admin(target.get("email")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除管理员账号")

    await db.users.delete_one({"_id": oid})
    logger.info(
        "管理员删除用户成功: admin=%s user_id=%s email=%s",
        mask_email(admin.get("email", "")), user_id, mask_email(target.get("email", "")),
    )
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str, payload: AdminResetPasswordRequest, admin: dict = Depends(get_current_admin)
):
    db = get_db()
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户 ID 非法")

    target = await db.users.find_one({"_id": oid})
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    new_hash = hash_password(payload.new_password)
    await db.users.update_one({"_id": oid}, {"$set": {"password_hash": new_hash}})
    logger.info(
        "管理员重置用户密码: admin=%s user_id=%s email=%s",
        mask_email(admin.get("email", "")), user_id, mask_email(target.get("email", "")),
    )
    return {"ok": True}


@router.patch("/users/{user_id}/credits", response_model=AdminUserItem)
async def update_credits(
    user_id: str, payload: AdminUpdateCreditsRequest, admin: dict = Depends(get_current_admin)
):
    db = get_db()
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户 ID 非法")

    result = await db.users.find_one_and_update(
        {"_id": oid}, {"$set": {"credits": payload.credits}}, return_document=True
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    logger.info(
        "管理员修改用户积分: admin=%s user_id=%s email=%s credits=%s",
        mask_email(admin.get("email", "")), user_id, mask_email(result.get("email", "")), payload.credits,
    )
    return _to_item(result)

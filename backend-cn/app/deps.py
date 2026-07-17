from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_db
from app.logger import get_logger
from app.security import decode_access_token, is_admin

_bearer = HTTPBearer(auto_error=False)

logger = get_logger("auth")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        logger.warning("鉴权失败(token 无效或已过期)")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")

    try:
        oid = ObjectId(user_id)
    except InvalidId:
        logger.warning("鉴权失败(token 中 user_id 非法): %s", user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")

    user = await get_db().users.find_one({"_id": oid})
    if user is None:
        logger.warning("鉴权失败(账号不存在): user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在")

    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求当前登录用户为管理员(邮箱在写死名单内)。"""
    if not is_admin(user.get("email")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限，仅管理员可操作")
    return user

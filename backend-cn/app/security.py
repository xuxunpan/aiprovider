from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 管理员邮箱名单(写死，不进配置)
# 该名单内的邮箱自动具备管理员权限，且不可被删除
ADMIN_EMAILS: frozenset[str] = frozenset(
    {
        "jifengbu000@163.com",
        "jifengbu@163.com",
        "sarahe6455@gmail.com",
    }
)


def is_admin(email: str | None) -> bool:
    """判断邮箱是否属于写死的管理员名单。"""
    return bool(email) and email.lower() in ADMIN_EMAILS


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None

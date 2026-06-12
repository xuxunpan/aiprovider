import os
import uuid

from app.config import settings
from app.logger import get_logger

logger = get_logger("storage")


def _user_dir(user_id: str) -> str:
    # 防止路径穿越：仅保留安全字符
    safe = "".join(c for c in user_id if c.isalnum())
    path = os.path.join(settings.storage_dir, safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_image(user_id: str, image_bytes: bytes, ext: str = "png") -> str:
    """保存图片，返回相对路径 {uid}/{file}。"""
    safe_uid = "".join(c for c in user_id if c.isalnum())
    directory = _user_dir(user_id)
    filename = f"{uuid.uuid4().hex}.{ext}"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    rel_path = f"{safe_uid}/{filename}"
    logger.info("图片已保存: path=%s 大小=%s 字节", rel_path, len(image_bytes))
    return rel_path


def resolve_path(rel_path: str) -> str | None:
    """将相对路径解析为绝对路径，校验未越出存储根目录。"""
    root = os.path.abspath(settings.storage_dir)
    full = os.path.abspath(os.path.join(root, rel_path))
    if not full.startswith(root + os.sep):
        logger.warning("拦截路径穿越尝试: rel_path=%s", rel_path)
        return None
    if not os.path.isfile(full):
        return None
    return full

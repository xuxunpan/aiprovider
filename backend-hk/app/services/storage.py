import os
import shutil
import uuid

from app.config import settings
from app.logger import get_logger

logger = get_logger("storage")


def _safe_name(identifier: str) -> str:
    return "".join(c for c in identifier if c.isalnum())


def _product_dir(product_id: str) -> str:
    safe = _safe_name(product_id)
    path = os.path.join(os.path.abspath(settings.storage_dir), safe)
    os.makedirs(path, exist_ok=True)
    return path


def _user_dir(user_id: str) -> str:
    safe = _safe_name(user_id)
    path = os.path.join(os.path.abspath(settings.storage_dir), safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_ref_image(product_id: str, image_bytes: bytes, ext: str, suffix: str = "") -> str:
    """保存参考图到产品目录，返回相对路径 {pid}/ref_{suffix}.{ext}。"""
    directory = _product_dir(product_id)
    safe_pid = _safe_name(product_id)
    if suffix:
        filename = f"ref_{suffix}.{ext}"
    else:
        filename = f"ref_{uuid.uuid4().hex[:8]}.{ext}"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    rel_path = f"{safe_pid}/{filename}"
    logger.info("参考图已保存: path=%s size=%s", rel_path, len(image_bytes))
    return rel_path


def save_generated_image(product_id: str, image_bytes: bytes) -> str:
    """保存生成图到产品目录，返回相对路径。"""
    directory = _product_dir(product_id)
    safe_pid = _safe_name(product_id)
    filename = f"generated_{uuid.uuid4().hex}.png"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    rel_path = f"{safe_pid}/{filename}"
    logger.info("生成图已保存: path=%s size=%s", rel_path, len(image_bytes))
    return rel_path


def save_image(user_id: str, image_bytes: bytes, ext: str = "png") -> str:
    """遗留兼容：按 user_id 保存图片，返回相对路径。"""
    safe_uid = _safe_name(user_id)
    directory = _user_dir(user_id)
    filename = f"{uuid.uuid4().hex}.{ext}"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    rel_path = f"{safe_uid}/{filename}"
    logger.info("图片已保存: path=%s size=%s", rel_path, len(image_bytes))
    return rel_path


def resolve_path(rel_path: str) -> str | None:
    """将相对路径解析为绝对路径，校验未越出存储根目录。"""
    root = os.path.abspath(settings.storage_dir)
    full = os.path.abspath(os.path.join(root, rel_path))
    if not full.startswith(root + os.sep) and full != root:
        logger.warning("拦截路径穿越尝试: rel_path=%s", rel_path)
        return None
    if not os.path.isfile(full):
        return None
    return full


def delete_product_dir(product_id: str) -> None:
    """删除产品目录及所有文件。"""
    directory = _product_dir(product_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
        logger.info("已删除产品目录: product_id=%s", product_id)

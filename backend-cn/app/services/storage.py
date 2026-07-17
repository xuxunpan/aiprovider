import os
import shutil
import uuid

from app.config import settings
from app.logger import get_logger

logger = get_logger("cn_storage")

_SAFE_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.()")


def _product_dir(product_id: str) -> str:
    safe = "".join(c for c in product_id if c.isalnum())
    path = os.path.join(os.path.abspath(settings.cn_storage_dir), safe)
    os.makedirs(path, exist_ok=True)
    return path


def resolve_path(rel_path: str) -> str | None:
    """将相对路径解析为绝对路径，校验未越出存储根目录。"""
    root = os.path.abspath(settings.cn_storage_dir)
    full = os.path.abspath(os.path.join(root, rel_path))
    if not full.startswith(root + os.sep) and full != root:
        logger.warning("拦截路径穿越尝试: rel_path=%s", rel_path)
        return None
    if not os.path.isfile(full):
        return None
    return full


def save_ref_image(product_id: str, image_bytes: bytes, ext: str) -> str:
    """保存参考图，返回文件名(不含目录)。"""
    directory = _product_dir(product_id)
    existing = [f for f in os.listdir(directory) if f.startswith("ref_")]
    idx = len(existing)
    filename = f"ref_{idx}.{ext}"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    logger.info("参考图已保存: product_id=%s file=%s size=%s", product_id, filename, len(image_bytes))
    return filename


def save_target_image(product_id: str, target_id: str, image_bytes: bytes) -> str:
    """保存生成的目标图到产品目录，返回相对路径 product_id/target_{hex}.png。"""
    directory = _product_dir(product_id)
    safe_tid = target_id
    filename = f"target_{safe_tid}.png"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    safe_pid = "".join(c for c in product_id if c.isalnum())
    rel_path = f"{safe_pid}/{filename}"
    logger.info("目标图已保存: path=%s size=%s", rel_path, len(image_bytes))
    return rel_path


def get_ref_images(product_id: str) -> list[tuple[bytes, str]]:
    """读取产品的所有参考图，返回 [(bytes, filename), ...]。"""
    directory = _product_dir(product_id)
    refs = sorted(
        [f for f in os.listdir(directory) if f.startswith("ref_")],
        key=lambda x: int(x.split("_")[1].split(".")[0]) if "_" in x and x.split("_")[1].split(".")[0].isdigit() else 0,
    )
    result: list[tuple[bytes, str]] = []
    for fn in refs:
        fp = os.path.join(directory, fn)
        with open(fp, "rb") as f:
            result.append((f.read(), fn))
    return result


def delete_target_image(product_id: str, target_id: str) -> None:
    """删除目标图文件（重新生成前清理旧文件）。"""
    directory = _product_dir(product_id)
    filename = f"target_{target_id}.png"
    full_path = os.path.join(directory, filename)
    if os.path.isfile(full_path):
        os.remove(full_path)
        logger.info("已删除目标图: path=%s", full_path)


def delete_product_dir(product_id: str) -> None:
    """删除产品整个文件夹。"""
    directory = _product_dir(product_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
        logger.info("已删除产品目录: product_id=%s", product_id)


# ── 聊天图片存储 ──────────────────────────────────────────────

def _chat_dir(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum())
    path = os.path.join(os.path.abspath(settings.cn_storage_dir), "chat", safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_chat_image(session_id: str, image_bytes: bytes, ext: str) -> str:
    """保存聊天上传图，返回相对路径 chat/{safe_sid}/{uuid}.{ext}。"""
    ext = ext.lower() if ext and ext.lower() in {"png", "jpg", "jpeg", "webp"} else "png"
    directory = _chat_dir(session_id)
    filename = f"{uuid.uuid4().hex}.{ext}"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    safe_sid = "".join(c for c in session_id if c.isalnum())
    rel_path = f"chat/{safe_sid}/{filename}"
    logger.info("聊天图片已保存: path=%s size=%s", rel_path, len(image_bytes))
    return rel_path


def resolve_chat_path(rel_path: str) -> str | None:
    """解析聊天图片相对路径为绝对路径，校验未越出存储根目录。"""
    root = os.path.abspath(settings.cn_storage_dir)
    full = os.path.abspath(os.path.join(root, rel_path))
    if not full.startswith(root + os.sep) and full != root:
        logger.warning("拦截路径穿越尝试(聊天): rel_path=%s", rel_path)
        return None
    if not os.path.isfile(full):
        return None
    return full


def delete_chat_dir(session_id: str) -> None:
    """删除会话的图片目录。"""
    safe = "".join(c for c in session_id if c.isalnum())
    directory = os.path.join(os.path.abspath(settings.cn_storage_dir), "chat", safe)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
        logger.info("已删除会话图片目录: session_id=%s", session_id)

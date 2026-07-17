"""每用户工作区管理：codex 在各自隔离的目录内运行（workspace_write 沙箱）。"""

import os
import shutil
import uuid

from app.config import settings
from app.logger import get_logger

logger = get_logger("workspace")

_VALID_EXTS = {"png", "jpg", "jpeg", "webp"}


def _safe_name(identifier: str) -> str:
    return "".join(c for c in identifier if c.isalnum())


def _workspaces_root() -> str:
    root = os.path.join(os.path.abspath(settings.storage_dir), "workspaces")
    os.makedirs(root, exist_ok=True)
    return root


def workspace_dir(user_id: str) -> str:
    """返回用户工作区绝对路径，按需创建。"""
    path = os.path.join(_workspaces_root(), _safe_name(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def uploads_dir(user_id: str) -> str:
    """返回用户上传图片目录绝对路径，按需创建。"""
    path = os.path.join(workspace_dir(user_id), "uploads")
    os.makedirs(path, exist_ok=True)
    return path


def save_upload(user_id: str, image_bytes: bytes, ext: str) -> str:
    """保存用户上传图片到工作区 uploads 目录，返回绝对路径（供 LocalImageInput 读取）。"""
    ext = ext.lower() if ext and ext.lower() in _VALID_EXTS else "png"
    directory = uploads_dir(user_id)
    filename = f"{uuid.uuid4().hex}.{ext}"
    full_path = os.path.join(directory, filename)
    with open(full_path, "wb") as f:
        f.write(image_bytes)
    logger.info("聊天上传图已保存: user_id=%s file=%s size=%s", user_id, filename, len(image_bytes))
    return full_path


def delete_workspace(user_id: str) -> None:
    """删除用户整个工作区目录。"""
    path = os.path.join(_workspaces_root(), _safe_name(user_id))
    if os.path.isdir(path):
        shutil.rmtree(path)
        logger.info("已删除用户工作区: user_id=%s", user_id)

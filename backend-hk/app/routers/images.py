from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.logger import get_logger
from app.services import storage

router = APIRouter(prefix="/internal", tags=["images"])

logger = get_logger("images")


@router.get("/images/{identifier}/{filename}")
async def get_image(identifier: str, filename: str):
    full = storage.resolve_path(f"{identifier}/{filename}")
    if full is None:
        logger.warning("图片文件未找到: id=%s filename=%s", identifier, filename)
        raise HTTPException(status_code=404, detail="not found")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    media_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
    media_type = media_map.get(ext, "image/png")
    return FileResponse(full, media_type=media_type)

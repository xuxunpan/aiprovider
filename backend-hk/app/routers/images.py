from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services import storage

router = APIRouter(prefix="/internal", tags=["images"])


@router.get("/images/{uid}/{filename}")
async def get_image(uid: str, filename: str):
    full = storage.resolve_path(f"{uid}/{filename}")
    if full is None:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(full, media_type="image/png")

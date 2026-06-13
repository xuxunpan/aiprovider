import asyncio
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.logger import get_logger
from app.services import openai_client, storage

router = APIRouter(prefix="/internal", tags=["generate"])

logger = get_logger("generate")

_VALID_EXTS = {"png", "jpg", "jpeg", "webp"}


def _infer_ext(filename: str | None) -> str:
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _VALID_EXTS:
            return ext
    return "png"


@router.post("/generate")
async def generate(
    user_id: str = Form(...),
    prompt: str = Form(...),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()
    if not image_bytes:
        logger.warning("生成请求被拒(图片为空): user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="empty image")

    logger.info("收到生成请求: user_id=%s 图片大小=%s 字节", user_id, len(image_bytes))

    if settings.mock_generate:
        logger.info("模拟生成: user_id=%s 等待 10s 后返回原图", user_id)
        await asyncio.sleep(10)
        ext = _infer_ext(image.filename)
        image_path = storage.save_image(user_id, image_bytes, ext=ext)
        logger.info("模拟生成完成: user_id=%s path=%s", user_id, image_path)
        return {"image_path": image_path}

    try:
        result_bytes = await openai_client.edit_image(
            prompt=prompt,
            image_bytes=image_bytes,
            filename=image.filename or "input.png",
        )
    except openai_client.OpenAIError as exc:
        logger.error("OpenAI 调用失败: user_id=%s 错误=%s", user_id, exc)
        raise HTTPException(status_code=502, detail=f"openai error: {exc}")

    image_path = storage.save_image(user_id, result_bytes, ext="png")
    logger.info("生成完成并保存: user_id=%s path=%s", user_id, image_path)
    return {"image_path": image_path}

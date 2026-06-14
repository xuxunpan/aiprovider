import asyncio
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

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
    product_id: str = Form(...),
    prompt: str = Form(...),
    images: List[UploadFile] = File(default=[]),
):
    ref_list: list[tuple[bytes, str]] = []
    for i, img in enumerate(images):
        img_bytes = await img.read()
        if not img_bytes:
            logger.warning("生成请求被拒(图片为空): product_id=%s", product_id)
            raise HTTPException(status_code=400, detail="empty image")
        ext = _infer_ext(img.filename)
        storage.save_ref_image(product_id, img_bytes, ext, suffix=str(i))
        ref_list.append((img_bytes, img.filename or f"ref_{i}.{ext}"))

    logger.info("收到生成请求: product_id=%s ref_count=%s prompt_len=%s",
                product_id, len(ref_list), len(prompt))

    if settings.mock_generate:
        if not ref_list:
            raise HTTPException(status_code=400, detail="模拟生成需要至少一张参考图")
        logger.info("模拟生成: product_id=%s 等待 10s 后返回原图", product_id)
        await asyncio.sleep(10)
        result_bytes = ref_list[0][0]
        storage.save_generated_image(product_id, result_bytes)
        logger.info("模拟生成完成: product_id=%s", product_id)
        return Response(content=result_bytes, media_type="image/png")

    try:
        result_bytes = await openai_client.edit_image(
            prompt=prompt,
            images=ref_list,
        )
    except openai_client.OpenAIError as exc:
        logger.error("OpenAI 调用失败: product_id=%s 错误=%s", product_id, exc)
        raise HTTPException(status_code=502, detail=f"openai error: {exc}")

    storage.save_generated_image(product_id, result_bytes)
    logger.info("生成完成并保存: product_id=%s size=%s", product_id, len(result_bytes))
    return Response(content=result_bytes, media_type="image/png")


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    storage.delete_product_dir(product_id)
    logger.info("已删除产品: product_id=%s", product_id)
    return {"ok": True}

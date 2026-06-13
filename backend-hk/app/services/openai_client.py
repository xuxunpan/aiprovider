import base64
import io
import time

from openai import AsyncOpenAI

from app.config import settings
from app.logger import get_logger

logger = get_logger("openai")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        _client = AsyncOpenAI(**kwargs)
    return _client


class OpenAIError(Exception):
    """OpenAI 调用失败。"""


async def edit_image(prompt: str, image_bytes: bytes, filename: str) -> bytes:
    """基于参考图 + 文字说明生成图片，返回图片字节(PNG)。"""
    client = _get_client()
    image_file = io.BytesIO(image_bytes)
    image_file.name = filename or "input.png"

    logger.info(
        "调用 OpenAI 图片编辑: model=%s size=%s prompt长度=%s",
        settings.openai_image_model, settings.openai_image_size, len(prompt),
    )
    started = time.monotonic()
    try:
        result = await client.images.edit(
            model=settings.openai_image_model,
            image=image_file,
            prompt=prompt,
            size=settings.openai_image_size,
        )
    except Exception as exc:  # openai SDK 各类异常统一上抛
        elapsed = time.monotonic() - started
        logger.error("OpenAI 调用异常: 耗时=%.2fs 错误=%s", elapsed, exc)
        raise OpenAIError(str(exc)) from exc

    elapsed = time.monotonic() - started
    if not result.data or not result.data[0].b64_json:
        logger.error("OpenAI 未返回图片数据: 耗时=%.2fs", elapsed)
        raise OpenAIError("OpenAI 未返回图片数据")

    logger.info("OpenAI 调用成功: 耗时=%.2fs", elapsed)
    return base64.b64decode(result.data[0].b64_json)

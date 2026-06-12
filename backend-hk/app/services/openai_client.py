import base64
import io

from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


class OpenAIError(Exception):
    """OpenAI 调用失败。"""


async def edit_image(prompt: str, image_bytes: bytes, filename: str) -> bytes:
    """基于参考图 + 文字说明生成图片，返回图片字节(PNG)。"""
    client = _get_client()
    image_file = io.BytesIO(image_bytes)
    image_file.name = filename or "input.png"

    try:
        result = await client.images.edit(
            model=settings.openai_image_model,
            image=image_file,
            prompt=prompt,
            size=settings.openai_image_size,
        )
    except Exception as exc:  # openai SDK 各类异常统一上抛
        raise OpenAIError(str(exc)) from exc

    if not result.data or not result.data[0].b64_json:
        raise OpenAIError("OpenAI 未返回图片数据")

    return base64.b64decode(result.data[0].b64_json)

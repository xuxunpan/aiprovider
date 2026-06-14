import base64
import time

from openai import AsyncOpenAI

from app.config import settings
from app.logger import get_logger

PROMPT_PREFIX = (
    "【核心规则】\n"
    "1. 忠实地保留产品原貌。不得改变、美化、创造或添加产品的形状、颜色、质地、材质、标记、比例或物理细节。\n"
    "2. 所有文案均应基于产品可见特征和用户提供的信息。切勿捏造功能、材料、认证、容量、兼容性、产地。\n"
)

logger = get_logger("openai")

_client: AsyncOpenAI | None = None

_VALID_EXTS = {"png", "jpg", "jpeg", "webp"}


def _infer_image_ext(filename: str | None) -> str:
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _VALID_EXTS:
            return ext
    return "png"


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


async def edit_image(prompt: str, images: list[tuple[bytes, str]] | None = None) -> bytes:
    """基于参考图 + 文字说明生成图片，返回图片字节(PNG)。

    images 为空时进行纯文字生图（Generate 模式）；
    有参考图时为基于原图的编辑生成（Edit 模式），全部参考图均传入。
    """
    client = _get_client()
    images = images or []

    content: list[dict] = [{"type": "input_text", "text": prompt}]
    for img_bytes, filename in images:
        ext = _infer_image_ext(filename)
        b64 = base64.b64encode(img_bytes).decode()
        content.append({
            "type": "input_image",
            "image_url": f"data:image/{ext};base64,{b64}",
        })

    logger.info(
        "调用 OpenAI Responses API: model=%s image_model=%s size=%s prompt_len=%s ref_count=%s",
        settings.openai_model, settings.openai_image_model,
        settings.openai_image_size, len(prompt), len(images),
    )
    started = time.monotonic()
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            instructions=PROMPT_PREFIX,
            input=[{"role": "user", "content": content}],
            tools=[{
                "type": "image_generation",
                "model": settings.openai_image_model,
                "size": settings.openai_image_size,
            }],
        )
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.error("OpenAI 调用异常: 耗时=%.2fs 错误=%s", elapsed, exc)
        raise OpenAIError(str(exc)) from exc

    elapsed = time.monotonic() - started
    for item in response.output:
        if getattr(item, "type", None) == "image_generation_call":
            if getattr(item, "status", None) == "completed":
                result = getattr(item, "result", None)
                if result:
                    logger.info("OpenAI 调用成功: 耗时=%.2fs", elapsed)
                    return base64.b64decode(result)

    logger.error("OpenAI 未返回图片数据: 耗时=%.2fs", elapsed)
    raise OpenAIError("OpenAI 未返回图片数据")

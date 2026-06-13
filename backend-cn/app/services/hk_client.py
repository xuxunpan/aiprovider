import time

import httpx

from app.config import settings
from app.logger import get_logger

logger = get_logger("hk_client")


class HKServiceError(Exception):
    """香港服务调用失败。"""


async def generate_image(
    product_id: str, prompt: str, ref_images: list[tuple[bytes, str]]
) -> bytes:
    """发送产品参考图+prompt 到香港网关生成图片，返回生成图字节。"""
    url = f"{settings.hk_base_url}/internal/generate"
    headers = {"X-Internal-Secret": settings.hk_internal_secret}
    data = {"product_id": product_id, "prompt": prompt}
    files = []
    for img_bytes, filename in ref_images:
        files.append(("images", (filename, img_bytes)))

    logger.info("调用香港网关生成图片: product_id=%s ref_count=%s", product_id, len(ref_images))
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.hk_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
    except httpx.RequestError as exc:
        elapsed = time.monotonic() - started
        logger.error("无法连接香港网关: product_id=%s 耗时=%.2fs 错误=%s", product_id, elapsed, exc)
        raise HKServiceError(f"无法连接图片生成服务: {exc}") from exc

    elapsed = time.monotonic() - started
    if resp.status_code != 200:
        detail = resp.text[:300] if resp.text else "未知错误"
        logger.error("香港网关返回错误: product_id=%s 状态码=%s 耗时=%.2fs detail=%s",
                     product_id, resp.status_code, elapsed, detail)
        raise HKServiceError(f"图片生成服务返回错误: {resp.status_code}")

    logger.info("香港网关生成成功: product_id=%s 耗时=%.2fs 图片大小=%s",
                product_id, elapsed, len(resp.content))
    return resp.content


async def delete_product_hk(product_id: str) -> None:
    """通知香港删除产品文件夹。"""
    url = f"{settings.hk_base_url}/internal/products/{product_id}"
    headers = {"X-Internal-Secret": settings.hk_internal_secret}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(url, headers=headers)
        if resp.status_code not in (200, 204):
            logger.warning("香港删除产品返回非200: product_id=%s status=%s", product_id, resp.status_code)
    except httpx.RequestError as exc:
        logger.warning("无法连接香港删除产品: product_id=%s error=%s", product_id, exc)

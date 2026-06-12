import httpx

from app.config import settings


class HKServiceError(Exception):
    """香港服务调用失败。"""


async def generate_image(user_id: str, prompt: str, image_bytes: bytes, filename: str) -> str:
    """调用香港 AI 网关生成图片，返回相对存储路径 {uid}/{file}。"""
    url = f"{settings.hk_base_url}/internal/generate"
    headers = {"X-Internal-Secret": settings.hk_internal_secret}
    data = {"user_id": user_id, "prompt": prompt}
    files = {"image": (filename, image_bytes)}

    try:
        async with httpx.AsyncClient(timeout=settings.hk_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
    except httpx.RequestError as exc:
        raise HKServiceError(f"无法连接图片生成服务: {exc}") from exc

    if resp.status_code != 200:
        raise HKServiceError(f"图片生成服务返回错误: {resp.status_code} {resp.text[:200]}")

    payload = resp.json()
    image_path = payload.get("image_path")
    if not image_path:
        raise HKServiceError("图片生成服务未返回有效结果")
    return image_path


async def open_image_stream(image_path: str) -> httpx.Response:
    """流式打开香港存储的图片，调用方负责关闭。"""
    url = f"{settings.hk_base_url}/internal/images/{image_path}"
    headers = {"X-Internal-Secret": settings.hk_internal_secret}
    client = httpx.AsyncClient(timeout=settings.hk_timeout_seconds)
    req = client.build_request("GET", url, headers=headers)
    resp = await client.send(req, stream=True)
    return resp

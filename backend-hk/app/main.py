import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.logger import get_logger, setup_logging

setup_logging(settings.log_level)

from app.routers import chat, generate, images
from app.services import codex_service

logger = get_logger("main")


class InternalSecretMiddleware(BaseHTTPMiddleware):
    """校验内部密钥：除 /health 外所有请求必须带正确的 X-Internal-Secret。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        secret = request.headers.get("X-Internal-Secret")
        if secret != settings.internal_secret:
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                "拒绝非法请求(密钥校验失败): ip=%s path=%s", client_ip, request.url.path
            )
            return JSONResponse(status_code=403, content={"detail": "forbidden"})
        return await call_next(request)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    os.makedirs(settings.storage_dir, exist_ok=True)
    os.makedirs(os.path.join(os.path.abspath(settings.storage_dir), "workspaces"), exist_ok=True)
    logger.info("香港网关启动中，存储目录: %s", settings.storage_dir)
    try:
        await codex_service.init_codex()
    except Exception as exc:
        logger.error("Codex 初始化失败，聊天功能不可用: %s", exc)
    yield
    await codex_service.close_codex()
    logger.info("香港网关已关闭")


app = FastAPI(title="AI Provider 香港网关", lifespan=lifespan)
app.add_middleware(InternalSecretMiddleware)

app.include_router(generate.router)
app.include_router(images.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

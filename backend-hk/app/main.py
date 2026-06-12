import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.routers import generate, images


class InternalSecretMiddleware(BaseHTTPMiddleware):
    """校验内部密钥：除 /health 外所有请求必须带正确的 X-Internal-Secret。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        secret = request.headers.get("X-Internal-Secret")
        if secret != settings.internal_secret:
            return JSONResponse(status_code=403, content={"detail": "forbidden"})
        return await call_next(request)


app = FastAPI(title="AI Provider 香港网关")
app.add_middleware(InternalSecretMiddleware)

app.include_router(generate.router)
app.include_router(images.router)


@app.on_event("startup")
async def _ensure_storage():
    os.makedirs(settings.storage_dir, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok"}

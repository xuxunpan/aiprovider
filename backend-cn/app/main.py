import asyncio

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import get_logger, setup_logging

setup_logging(settings.log_level)

from app.db import close_db, connect_db
from app.routers import auth, credits, products

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("国内主后端启动中...")
    await connect_db()

    from app.services import queue_service
    dispatcher_task = asyncio.create_task(queue_service.dispatcher_loop())

    yield

    dispatcher_task.cancel()
    try:
        await dispatcher_task
    except asyncio.CancelledError:
        pass

    await close_db()
    logger.info("国内主后端已关闭")


app = FastAPI(title="AI Provider 国内主后端", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(credits.router)
app.include_router(products.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

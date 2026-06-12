from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger
from app.schemas.image import GenerateResponse
from app.services import credit_service as cs
from app.services import hk_client

router = APIRouter(prefix="/api/images", tags=["images"])

logger = get_logger("images")

_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    prompt: str = Form(...),
    image: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    user_id = user["_id"]
    if image.content_type not in _ALLOWED_TYPES:
        logger.warning("生成请求被拒(图片格式不支持): user_id=%s type=%s", user_id, image.content_type)
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、WEBP 格式的图片")

    image_bytes = await image.read()
    if len(image_bytes) == 0:
        logger.warning("生成请求被拒(图片为空): user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="上传的图片为空")
    if len(image_bytes) > settings.max_upload_bytes:
        logger.warning(
            "生成请求被拒(图片过大): user_id=%s size=%s", user_id, len(image_bytes)
        )
        raise HTTPException(status_code=400, detail=f"图片大小不能超过 {settings.max_upload_mb}MB")

    prompt = prompt.strip()
    if not prompt:
        logger.warning("生成请求被拒(说明文字为空): user_id=%s", user_id)
        raise HTTPException(status_code=400, detail="请输入图片说明文字")

    db = get_db()
    cost = settings.cost_per_image

    logger.info("收到图片生成请求: user_id=%s 图片大小=%s 字节 prompt长度=%s", user_id, len(image_bytes), len(prompt))

    # 预扣积分(原子操作)
    reserved = await cs.try_reserve_credits(db, user_id, cost)
    if not reserved:
        logger.warning("预扣积分失败(余额不足): user_id=%s 需要=%s", user_id, cost)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="积分已用完，请充值后继续使用",
        )

    task_id = await cs.create_task(db, user_id, prompt, cost)
    logger.info("已预扣积分并创建任务: user_id=%s task_id=%s cost=%s", user_id, task_id, cost)

    try:
        image_path = await hk_client.generate_image(
            user_id=str(user_id),
            prompt=prompt,
            image_bytes=image_bytes,
            filename=image.filename or "upload.png",
        )
    except hk_client.HKServiceError as exc:
        await cs.refund_credits(db, user_id, cost)
        await cs.mark_task_failed(db, task_id, "调用图片生成服务失败")
        logger.error(
            "图片生成失败已退还积分: user_id=%s task_id=%s cost=%s 原因=%s",
            user_id, task_id, cost, exc,
        )
        raise HTTPException(status_code=502, detail="图片生成失败，已退还积分，请稍后重试")
    except Exception:
        await cs.refund_credits(db, user_id, cost)
        await cs.mark_task_failed(db, task_id, "未知错误")
        logger.exception("图片生成发生未知错误已退还积分: user_id=%s task_id=%s", user_id, task_id)
        raise HTTPException(status_code=500, detail="图片生成失败，已退还积分，请稍后重试")

    await cs.mark_task_success(db, task_id, image_path)
    credits = await cs.get_credits(db, user_id)
    logger.info(
        "图片生成成功: user_id=%s task_id=%s 剩余积分=%s", user_id, task_id, credits
    )

    return GenerateResponse(
        task_id=str(task_id),
        status="success",
        image_url=f"/api/images/{task_id}",
        credits=credits,
    )


@router.get("/{task_id}")
async def get_image(task_id: str, user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(task_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="图片不存在")

    db = get_db()
    task = await db.tasks.find_one({"_id": oid})
    if task is None or task["user_id"] != user["_id"]:
        logger.warning("图片访问被拒(不存在或非本人): user_id=%s task_id=%s", user["_id"], task_id)
        raise HTTPException(status_code=404, detail="图片不存在")
    if task["status"] != "success" or not task.get("hk_image_path"):
        raise HTTPException(status_code=404, detail="图片尚未生成完成")

    upstream = await hk_client.open_image_stream(task["hk_image_path"])
    if upstream.status_code != 200:
        await upstream.aclose()
        logger.error(
            "读取香港图片失败: user_id=%s task_id=%s 状态码=%s",
            user["_id"], task_id, upstream.status_code,
        )
        raise HTTPException(status_code=502, detail="图片读取失败，请稍后重试")

    media_type = upstream.headers.get("content-type", "image/png")

    async def _iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )

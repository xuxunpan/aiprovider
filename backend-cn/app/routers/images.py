from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.schemas.image import GenerateResponse
from app.services import credit_service as cs
from app.services import hk_client

router = APIRouter(prefix="/api/images", tags=["images"])

_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    prompt: str = Form(...),
    image: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if image.content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、WEBP 格式的图片")

    image_bytes = await image.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="上传的图片为空")
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"图片大小不能超过 {settings.max_upload_mb}MB")

    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请输入图片说明文字")

    db = get_db()
    user_id = user["_id"]
    cost = settings.cost_per_image

    # 预扣积分(原子操作)
    reserved = await cs.try_reserve_credits(db, user_id, cost)
    if not reserved:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="积分已用完，请充值后继续使用",
        )

    task_id = await cs.create_task(db, user_id, prompt, cost)

    try:
        image_path = await hk_client.generate_image(
            user_id=str(user_id),
            prompt=prompt,
            image_bytes=image_bytes,
            filename=image.filename or "upload.png",
        )
    except hk_client.HKServiceError:
        await cs.refund_credits(db, user_id, cost)
        await cs.mark_task_failed(db, task_id, "调用图片生成服务失败")
        raise HTTPException(status_code=502, detail="图片生成失败，已退还积分，请稍后重试")
    except Exception:
        await cs.refund_credits(db, user_id, cost)
        await cs.mark_task_failed(db, task_id, "未知错误")
        raise HTTPException(status_code=500, detail="图片生成失败，已退还积分，请稍后重试")

    await cs.mark_task_success(db, task_id, image_path)
    credits = await cs.get_credits(db, user_id)

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
        raise HTTPException(status_code=404, detail="图片不存在")
    if task["status"] != "success" or not task.get("hk_image_path"):
        raise HTTPException(status_code=404, detail="图片尚未生成完成")

    upstream = await hk_client.open_image_stream(task["hk_image_path"])
    if upstream.status_code != 200:
        await upstream.aclose()
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

import os

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logger import get_logger
from app.schemas.product import (
    CreateTargetRequest,
    ProductListItem,
    ProductListOut,
    ProductOut,
    RefImageOut,
    RegenerateRequest,
    TargetCreated,
    TargetOut,
)
from app.services import credit_service as cs
from app.services import hk_client, image_utils, storage

router = APIRouter(prefix="/api", tags=["products"])

logger = get_logger("products")

_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}


def _ext_from_content_type(ct: str | None) -> str:
    if ct and "/" in ct:
        ext = ct.rsplit("/", 1)[-1].lower()
        if ext in _ALLOWED_EXTS:
            return ext
    return "png"


def _target_out(doc: dict) -> TargetOut:
    tid = str(doc["_id"])
    image_url = None
    if doc.get("cn_image_path"):
        image_url = f"/api/products/{doc['product_id']}/files/target_{tid}.png"
    return TargetOut(
        id=tid,
        prompt=doc.get("prompt", ""),
        status=doc["status"],
        cost=doc.get("cost", 0),
        image_url=image_url,
        error_msg=doc.get("error_msg"),
        created_at=doc["created_at"],
        started_at=doc.get("started_at"),
        finished_at=doc.get("finished_at"),
    )


# ── 产品 CRUD ──────────────────────────────────────────────

@router.post("/products", status_code=201)
async def create_product(
    name: str = Form(...),
    images: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    user_id = user["_id"]
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请输入产品名称")
    if not images:
        raise HTTPException(status_code=400, detail="请至少上传一张参考图")

    db = get_db()
    product_id = ObjectId()
    ref_records: list[dict] = []

    for img in images:
        if img.content_type not in _ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、WEBP 格式的图片")
        img_bytes = await img.read()
        if not img_bytes:
            raise HTTPException(status_code=400, detail="上传的图片为空")
        if len(img_bytes) > settings.max_upload_bytes:
            raise HTTPException(status_code=400, detail=f"图片大小不能超过 {settings.max_upload_mb}MB")

        img_bytes = image_utils.resize_if_needed(img_bytes, settings.max_image_dimension)

        ext = _ext_from_content_type(img.content_type)
        filename = storage.save_ref_image(str(product_id), img_bytes, ext)
        ref_records.append({"path": filename, "filename": img.filename or filename})

    doc = {
        "_id": product_id,
        "user_id": user_id,
        "name": name,
        "ref_images": ref_records,
        "created_at": product_id.generation_time,
        "updated_at": product_id.generation_time,
    }
    await db.products.insert_one(doc)
    logger.info("产品已创建: product_id=%s user_id=%s", product_id, user_id)
    return {"product_id": str(product_id)}


@router.get("/products", response_model=ProductListOut)
async def list_products(user: dict = Depends(get_current_user)):
    db = get_db()
    cursor = db.products.find({"user_id": user["_id"]}).sort("created_at", -1)
    items: list[ProductListItem] = []
    async for prod in cursor:
        pid = prod["_id"]
        target_pipeline = [
            {"$match": {"product_id": pid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        summary: dict[str, int] = {}
        async for grp in db.targets.aggregate(target_pipeline):
            summary[grp["_id"]] = grp["count"]
        target_count = sum(summary.values())
        items.append(ProductListItem(
            id=str(pid),
            name=prod["name"],
            ref_count=len(prod.get("ref_images", [])),
            target_count=target_count,
            target_status_summary=summary,
            created_at=prod["created_at"],
            updated_at=prod["updated_at"],
        ))
    return ProductListOut(products=items)


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        pid = ObjectId(product_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="产品不存在")
    prod = await db.products.find_one({"_id": pid})
    if not prod or prod["user_id"] != user["_id"]:
        raise HTTPException(status_code=404, detail="产品不存在")

    refs = [
        RefImageOut(path=r["path"], filename=r.get("filename", r["path"]))
        for r in prod.get("ref_images", [])
    ]
    cursor = db.targets.find({"product_id": pid}).sort("created_at", 1)
    targets = [_target_out(t) async for t in cursor]

    return ProductOut(
        id=str(pid),
        name=prod["name"],
        ref_images=refs,
        targets=targets,
        created_at=prod["created_at"],
        updated_at=prod["updated_at"],
    )


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        pid = ObjectId(product_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="产品不存在")
    prod = await db.products.find_one({"_id": pid})
    if not prod or prod["user_id"] != user["_id"]:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 删本地文件
    storage.delete_product_dir(str(pid))
    # 删香港文件
    await hk_client.delete_product_hk(str(pid))
    # 删 Mongo 记录
    await db.targets.delete_many({"product_id": pid})
    await db.products.delete_one({"_id": pid})
    logger.info("产品已删除: product_id=%s", pid)
    return {"ok": True}


# ── 目标图 ──────────────────────────────────────────────────

@router.post("/products/{product_id}/targets", status_code=201, response_model=TargetCreated)
async def create_target(
    product_id: str,
    body: CreateTargetRequest,
    user: dict = Depends(get_current_user),
):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请输入目标图提示词")

    db = get_db()
    try:
        pid = ObjectId(product_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="产品不存在")
    prod = await db.products.find_one({"_id": pid})
    if not prod or prod["user_id"] != user["_id"]:
        raise HTTPException(status_code=404, detail="产品不存在")
    if not prod.get("ref_images"):
        raise HTTPException(status_code=400, detail="请先上传产品参考图")

    cost = settings.cost_per_image
    reserved = await cs.try_reserve_credits(db, user["_id"], cost)
    if not reserved:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="积分已用完，请充值后继续使用",
        )

    target_id = await cs.create_target(db, pid, user["_id"], prompt, cost)
    return TargetCreated(target_id=str(target_id), status="queued")


@router.post("/targets/{target_id}/regenerate", response_model=TargetCreated)
async def regenerate_target(
    target_id: str,
    body: RegenerateRequest,
    user: dict = Depends(get_current_user),
):
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请输入目标图提示词")

    db = get_db()
    try:
        tid = ObjectId(target_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="目标图不存在")
    target = await db.targets.find_one({"_id": tid})
    if not target or target["user_id"] != user["_id"]:
        raise HTTPException(status_code=404, detail="目标图不存在")

    # 预扣积分
    cost = settings.cost_per_image
    reserved = await cs.try_reserve_credits(db, user["_id"], cost)
    if not reserved:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="积分已用完，请充值后继续使用",
        )

    # 删除旧图片文件
    if target.get("cn_image_path"):
        storage.delete_target_image(str(target["product_id"]), str(tid))

    # 重置为排队
    await db.targets.update_one(
        {"_id": tid},
        {
            "$set": {
                "prompt": prompt,
                "status": "queued",
                "cost": cost,
                "cn_image_path": None,
                "error_msg": None,
                "started_at": None,
                "finished_at": None,
            }
        },
    )
    logger.info("目标图重新生成入队: target_id=%s", tid)
    return TargetCreated(target_id=str(tid), status="queued")


@router.get("/targets/{target_id}", response_model=TargetOut)
async def get_target(target_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        tid = ObjectId(target_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="目标图不存在")
    target = await db.targets.find_one({"_id": tid})
    if not target or target["user_id"] != user["_id"]:
        raise HTTPException(status_code=404, detail="目标图不存在")
    return _target_out(target)


# ── 图片文件服务（从 CN 本地读取） ──────────────────────────

@router.get("/products/{product_id}/files/{filename}")
async def serve_product_file(
    product_id: str,
    filename: str,
    user: dict = Depends(get_current_user),
):
    """直接从 CN 本地存储提供图片文件（参考图 / 目标图）。"""
    db = get_db()
    try:
        pid = ObjectId(product_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="文件不存在")

    prod = await db.products.find_one({"_id": pid})
    if not prod or prod["user_id"] != user["_id"]:
        raise HTTPException(status_code=404, detail="文件不存在")

    safe_pid = "".join(c for c in product_id if c.isalnum())
    rel_path = f"{safe_pid}/{filename}"
    full = storage.resolve_path(rel_path)
    if full is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    media_type = f"image/{ext}" if ext in _ALLOWED_EXTS else "image/png"
    return FileResponse(
        full,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )

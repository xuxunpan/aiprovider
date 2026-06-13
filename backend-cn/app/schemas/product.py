from datetime import datetime

from pydantic import BaseModel


class RefImageOut(BaseModel):
    path: str
    filename: str


class TargetOut(BaseModel):
    id: str
    prompt: str
    status: str
    cost: int
    image_url: str | None = None
    error_msg: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ProductOut(BaseModel):
    id: str
    name: str
    ref_images: list[RefImageOut]
    targets: list[TargetOut]
    created_at: datetime
    updated_at: datetime


class ProductListItem(BaseModel):
    id: str
    name: str
    ref_count: int
    target_count: int
    target_status_summary: dict[str, int]
    created_at: datetime
    updated_at: datetime


class ProductListOut(BaseModel):
    products: list[ProductListItem]


class CreateTargetRequest(BaseModel):
    prompt: str


class TargetCreated(BaseModel):
    target_id: str
    status: str


class RegenerateRequest(BaseModel):
    prompt: str

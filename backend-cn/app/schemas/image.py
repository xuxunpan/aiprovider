from datetime import datetime

from pydantic import BaseModel


class GenerateResponse(BaseModel):
    task_id: str
    status: str
    image_url: str
    credits: int


class TaskResponse(BaseModel):
    task_id: str
    prompt: str
    status: str
    cost: int
    image_url: str | None
    error_msg: str | None
    created_at: datetime

from datetime import datetime

from pydantic import BaseModel


class RechargeRecordOut(BaseModel):
    id: str
    amount_credits: int
    price: float
    status: str
    created_at: datetime


class RechargeRecordsOut(BaseModel):
    records: list[RechargeRecordOut]

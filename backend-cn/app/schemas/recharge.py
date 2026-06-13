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


class RechargePackageOut(BaseModel):
    id: str
    credits: int
    price: float


class RechargePackagesOut(BaseModel):
    packages: list[RechargePackageOut]


class CreateRechargeRecordRequest(BaseModel):
    package_id: str


class CreateRechargeRecordOut(BaseModel):
    ok: bool
    record_id: str

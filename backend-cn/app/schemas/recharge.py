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


class RechargeResponse(BaseModel):
    """下单充值响应——含 record_id 与 code_url(微信已配置时)。"""
    record_id: str
    code_url: str | None = None
    message: str | None = None


class RechargeStatusOut(BaseModel):
    """充值记录状态查询响应。"""
    record_id: str
    status: str
    amount_credits: int
    price: float

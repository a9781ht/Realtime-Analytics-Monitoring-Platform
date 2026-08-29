"""資料分析與系統管理 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StatsSummary(BaseModel):
    count: int
    total: float | None
    average: float | None
    minimum: float | None
    maximum: float | None
    start_time: datetime | None = None
    end_time: datetime | None = None


class CategoryAggregate(BaseModel):
    category: str
    count: int
    total: float
    average: float
    minimum: float
    maximum: float


class TrendPoint(BaseModel):
    bucket: str
    count: int
    total: float
    average: float


class SystemLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    action: str
    message: str | None
    method: str | None
    path: str | None
    status_code: int | None
    duration_ms: int | None
    client_ip: str | None
    user_id: int | None
    created_at: datetime


class TableStat(BaseModel):
    table: str
    rows: int


class DatabaseStatus(BaseModel):
    connected: bool
    dialect: str
    pool: dict
    tables: list[TableStat]
    server_time: datetime | None = None

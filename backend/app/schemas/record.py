"""資料記錄相關 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DataRecordBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, examples=["生產線 A 溫度"])
    value: float = Field(..., examples=[36.5])
    category: str = Field(..., min_length=1, max_length=50, examples=["temperature"])
    description: str | None = Field(default=None, max_length=2000)
    recorded_at: datetime | None = Field(default=None, description="資料發生時間，未填則為現在")


class DataRecordCreate(DataRecordBase):
    pass


class DataRecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    value: float | None = None
    category: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    recorded_at: datetime | None = None


class DataRecordRead(DataRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recorded_at: datetime
    owner_id: int
    owner_username: str | None = None
    created_at: datetime
    updated_at: datetime


class BulkImportItem(DataRecordBase):
    pass


class BulkImportRequest(BaseModel):
    items: list[BulkImportItem] = Field(..., min_length=1, max_length=5000)


class BulkImportResult(BaseModel):
    inserted: int
    failed: int
    errors: list[str] = []

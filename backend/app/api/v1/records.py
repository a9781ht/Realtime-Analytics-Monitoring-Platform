"""資料記錄 API：CRUD、分頁查詢、批量匯入（CSV / JSON）。"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbSession, require_editor
from app.core.exceptions import AppError
from app.models.record import DataRecord
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.record import (
    BulkImportItem,
    BulkImportRequest,
    BulkImportResult,
    DataRecordCreate,
    DataRecordRead,
    DataRecordUpdate,
)
from app.services import log_service, record_service

router = APIRouter(prefix="/records", tags=["Records 資料管理"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def _to_read(record: DataRecord) -> DataRecordRead:
    data = DataRecordRead.model_validate(record)
    data.owner_username = record.owner.username if record.owner else None
    return data


@router.get("", response_model=Page[DataRecordRead], summary="查詢資料（分頁 / 篩選 / 排序）")
async def list_records(
    db: DbSession,
    _: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 20,
    keyword: Annotated[str | None, Query(description="標題關鍵字")] = None,
    category: str | None = None,
    owner_id: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    sort_by: Annotated[str, Query(pattern="^(id|title|value|category|recorded_at|created_at)$")] = "recorded_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[DataRecordRead]:
    records, total = await record_service.list_records(
        db,
        page=page,
        size=size,
        keyword=keyword,
        category=category,
        owner_id=owner_id,
        min_value=min_value,
        max_value=max_value,
        start_time=start_time,
        end_time=end_time,
        sort_by=sort_by,
        order=order,
    )
    return Page.create([_to_read(record) for record in records], total, page, size)


@router.get("/categories", response_model=list[str], summary="取得所有分類")
async def list_categories(db: DbSession, _: CurrentUser) -> list[str]:
    return await record_service.list_categories(db)


@router.get("/{record_id}", response_model=DataRecordRead, summary="查詢單筆資料")
async def get_record(record_id: int, db: DbSession, _: CurrentUser) -> DataRecordRead:
    return _to_read(await record_service.get_record(db, record_id))


@router.post(
    "",
    response_model=DataRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="建立資料（Admin / User）",
)
async def create_record(
    payload: DataRecordCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(require_editor)],
) -> DataRecordRead:
    record = await record_service.create_record(db, payload, current_user)
    await log_service.write_log(
        level="INFO",
        action="record.create",
        message=f"{current_user.username} 建立資料 id={record.id}",
        user_id=current_user.id,
    )
    return _to_read(record)


@router.put("/{record_id}", response_model=DataRecordRead, summary="整筆更新（建立者或 Admin）")
async def replace_record(
    record_id: int,
    payload: DataRecordCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(require_editor)],
) -> DataRecordRead:
    record = await record_service.update_record(
        db, record_id, DataRecordUpdate(**payload.model_dump()), current_user
    )
    return _to_read(record)


@router.patch("/{record_id}", response_model=DataRecordRead, summary="部分更新（建立者或 Admin）")
async def update_record(
    record_id: int,
    payload: DataRecordUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(require_editor)],
) -> DataRecordRead:
    record = await record_service.update_record(db, record_id, payload, current_user)
    await log_service.write_log(
        level="INFO",
        action="record.update",
        message=f"{current_user.username} 更新資料 id={record_id}",
        user_id=current_user.id,
    )
    return _to_read(record)


@router.delete("/{record_id}", response_model=Message, summary="刪除資料（建立者或 Admin）")
async def delete_record(
    record_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(require_editor)],
) -> Message:
    await record_service.delete_record(db, record_id, current_user)
    await log_service.write_log(
        level="WARNING",
        action="record.delete",
        message=f"{current_user.username} 刪除資料 id={record_id}",
        user_id=current_user.id,
    )
    return Message(message="資料已刪除")


@router.post(
    "/bulk",
    response_model=BulkImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="批量匯入（JSON）",
)
async def bulk_import_json(
    payload: BulkImportRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(require_editor)],
) -> BulkImportResult:
    inserted, failed, errors = await record_service.bulk_create(db, payload.items, current_user)
    return BulkImportResult(inserted=inserted, failed=failed, errors=errors)


@router.post(
    "/import",
    response_model=BulkImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="批量匯入（上傳 CSV 或 JSON 檔案）",
)
async def bulk_import_file(
    db: DbSession,
    current_user: Annotated[User, Depends(require_editor)],
    file: Annotated[UploadFile, File(description="CSV 或 JSON 檔案，欄位：title,value,category,description,recorded_at")],
) -> BulkImportResult:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise AppError("檔案過大，請小於 5MB", code="file_too_large")

    filename = (file.filename or "").lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("檔案編碼需為 UTF-8", code="invalid_encoding") from exc

    raw_rows: list[dict]
    if filename.endswith(".json"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AppError(f"JSON 解析失敗：{exc}", code="invalid_json") from exc
        raw_rows = parsed if isinstance(parsed, list) else parsed.get("items", [])
    elif filename.endswith(".csv"):
        raw_rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise AppError("僅支援 .csv 或 .json 檔案", code="unsupported_file_type")

    if not raw_rows:
        raise AppError("檔案內容為空", code="empty_file")
    if len(raw_rows) > 5000:
        raise AppError("單次匯入上限 5000 筆", code="too_many_rows")

    items: list[BulkImportItem] = []
    errors: list[str] = []
    for index, row in enumerate(raw_rows, start=1):
        cleaned = {key: (value if value not in ("", None) else None) for key, value in row.items()}
        try:
            items.append(BulkImportItem(**cleaned))
        except (ValidationError, TypeError) as exc:
            errors.append(f"第 {index} 列匯入失敗：{exc.__class__.__name__}")

    inserted, _, insert_errors = await record_service.bulk_create(db, items, current_user)
    errors.extend(insert_errors)

    await log_service.write_log(
        level="INFO",
        action="record.import",
        message=f"{current_user.username} 匯入 {inserted} 筆（來源 {file.filename}）",
        user_id=current_user.id,
    )
    return BulkImportResult(inserted=inserted, failed=len(raw_rows) - inserted, errors=errors[:20])

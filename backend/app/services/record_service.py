"""資料記錄業務邏輯（全部使用 SQLAlchemy ORM，無原生 SQL）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import UserRole
from app.models.record import DataRecord
from app.models.user import User
from app.schemas.record import BulkImportItem, DataRecordCreate, DataRecordUpdate

SORTABLE_FIELDS = {
    "id": DataRecord.id,
    "title": DataRecord.title,
    "value": DataRecord.value,
    "category": DataRecord.category,
    "recorded_at": DataRecord.recorded_at,
    "created_at": DataRecord.created_at,
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_can_modify(record: DataRecord, user: User) -> None:
    """僅創建者本人或 Admin 可修改/刪除。"""
    if user.role != UserRole.ADMIN and record.owner_id != user.id:
        raise PermissionDeniedError("僅資料建立者或管理員可執行此操作")


async def get_record(db: AsyncSession, record_id: int) -> DataRecord:
    stmt = (
        select(DataRecord)
        .options(selectinload(DataRecord.owner))
        .where(DataRecord.id == record_id)
    )
    record = (await db.execute(stmt)).unique().scalar_one_or_none()
    if record is None:
        raise NotFoundError("找不到指定資料記錄")
    return record


async def list_records(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    keyword: str | None = None,
    category: str | None = None,
    owner_id: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    sort_by: str = "recorded_at",
    order: str = "desc",
) -> tuple[list[DataRecord], int]:
    stmt = select(DataRecord).options(selectinload(DataRecord.owner))
    count_stmt = select(func.count()).select_from(DataRecord)

    conditions = []
    if keyword:
        conditions.append(DataRecord.title.like(f"%{keyword}%"))
    if category:
        conditions.append(DataRecord.category == category)
    if owner_id is not None:
        conditions.append(DataRecord.owner_id == owner_id)
    if min_value is not None:
        conditions.append(DataRecord.value >= min_value)
    if max_value is not None:
        conditions.append(DataRecord.value <= max_value)
    if start_time is not None:
        conditions.append(DataRecord.recorded_at >= start_time)
    if end_time is not None:
        conditions.append(DataRecord.recorded_at <= end_time)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    column = SORTABLE_FIELDS.get(sort_by, DataRecord.recorded_at)
    stmt = stmt.order_by(desc(column) if order.lower() == "desc" else asc(column))
    stmt = stmt.offset((page - 1) * size).limit(size)

    records = list((await db.execute(stmt)).unique().scalars().all())
    return records, total


async def create_record(db: AsyncSession, payload: DataRecordCreate, owner: User) -> DataRecord:
    record = DataRecord(
        title=payload.title,
        value=payload.value,
        category=payload.category,
        description=payload.description,
        recorded_at=payload.recorded_at or _now(),
        owner_id=owner.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return await get_record(db, record.id)


async def update_record(
    db: AsyncSession, record_id: int, payload: DataRecordUpdate, user: User
) -> DataRecord:
    record = await get_record(db, record_id)
    ensure_can_modify(record, user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(record, field, value)

    await db.commit()
    await db.refresh(record)
    return record


async def delete_record(db: AsyncSession, record_id: int, user: User) -> None:
    record = await get_record(db, record_id)
    ensure_can_modify(record, user)
    await db.delete(record)
    await db.commit()


async def bulk_create(
    db: AsyncSession, items: list[BulkImportItem], owner: User
) -> tuple[int, int, list[str]]:
    """批次匯入資料，回傳 (成功筆數, 失敗筆數, 錯誤訊息)。"""
    records: list[DataRecord] = []
    errors: list[str] = []

    for index, item in enumerate(items, start=1):
        try:
            records.append(
                DataRecord(
                    title=item.title,
                    value=float(item.value),
                    category=item.category,
                    description=item.description,
                    recorded_at=item.recorded_at or _now(),
                    owner_id=owner.id,
                )
            )
        except (TypeError, ValueError) as exc:
            errors.append(f"第 {index} 筆資料格式錯誤：{exc}")

    if records:
        db.add_all(records)
        await db.commit()

    return len(records), len(items) - len(records), errors


async def list_categories(db: AsyncSession) -> list[str]:
    stmt = select(DataRecord.category).distinct().order_by(DataRecord.category.asc())
    return [row for row in (await db.execute(stmt)).scalars().all()]

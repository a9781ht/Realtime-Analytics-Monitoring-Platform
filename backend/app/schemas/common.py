"""共用 Pydantic Schema（分頁、訊息回應）。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Message(BaseModel):
    message: str = Field(..., description="操作結果描述")


class PageMeta(BaseModel):
    total: int = Field(..., description="符合條件的總筆數")
    page: int = Field(..., description="目前頁碼（1 起算）")
    size: int = Field(..., description="每頁筆數")
    pages: int = Field(..., description="總頁數")


class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def create(cls, items: list[T], total: int, page: int, size: int) -> "Page[T]":
        pages = (total + size - 1) // size if size else 0
        return cls(items=items, meta=PageMeta(total=total, page=page, size=size, pages=pages))

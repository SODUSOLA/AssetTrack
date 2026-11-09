from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 100


class PageParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


Pagination = Annotated[PageParams, Depends()]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


def paginate(db: Session, stmt: Select[Any], params: PageParams) -> tuple[list[Any], int]:
    """Run an ordered ORM select with limit/offset; returns (rows, total)."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(params.page_size).offset(params.offset)).all()
    return list(rows), total


def to_page[T: BaseModel](
    schema: type[T], rows: list[Any], total: int, params: PageParams
) -> Page[T]:
    return Page[T](
        items=[schema.model_validate(r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )

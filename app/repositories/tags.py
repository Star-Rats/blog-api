"""标签数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Article, Tag


def list_all(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name.asc())).all())


def list_with_published_count(db: Session, limit: int | None = None) -> list[tuple[Tag, int]]:
    """标签及其已发布文章数，按文章数倒序。"""
    stmt = (
        select(Tag, func.count(Article.id))
        .join(Article.tags)
        .where(Article.status == 1)
        .group_by(Tag.id)
        .order_by(func.count(Article.id).desc(), Tag.name.asc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return [(tag, count) for tag, count in db.execute(stmt).all()]

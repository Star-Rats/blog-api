"""文章数据访问：前台/管理端的查询封装。

只做数据存取，不负责业务规则校验与跨操作事务（那些在 services）。
"""
from __future__ import annotations

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.db.models import Article, Tag


def _published_stmt() -> Select:
    """已发布文章的基础查询（前台可见性规则统一在这里）。"""
    return (
        select(Article)
        .options(joinedload(Article.category), joinedload(Article.tags))
        .where(Article.status == 1)
    )


def list_published(
    db: Session,
    page: int,
    page_size: int,
    *,
    category_id: int | None = None,
    tag_id: int | None = None,
    keyword: str | None = None,
) -> tuple[list[Article], int]:
    """已发布文章分页列表，支持分类/标签/关键词过滤，返回 (列表, 总数)。"""
    stmt = _published_stmt()
    if category_id:
        stmt = stmt.where(Article.category_id == category_id)
    if tag_id:
        stmt = stmt.where(Article.tags.any(Tag.id == tag_id))
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Article.title.like(like),
                Article.description.like(like),
                Article.body_text.like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Article.published_at.desc(), Article.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return list(rows), total


def list_published_all(db: Session) -> list[Article]:
    """全部已发布文章（归档页聚合用），按发布时间倒序。"""
    return list(
        db.scalars(
            _published_stmt().order_by(Article.published_at.desc(), Article.id.desc())
        ).unique().all()
    )


def recent_published(db: Session, limit: int = 6) -> list[Article]:
    return list(
        db.scalars(
            _published_stmt().order_by(Article.published_at.desc(), Article.id.desc()).limit(limit)
        ).unique().all()
    )


def count_published(db: Session) -> int:
    return db.scalar(select(func.count(Article.id)).where(Article.status == 1)) or 0


def get_published_by_slug(db: Session, slug: str) -> Article | None:
    return db.scalar(_published_stmt().where(Article.slug == slug))


def increment_views(db: Session, article_id: int) -> None:
    """浏览量 +1（原子自增，独立小事务）。"""
    db.execute(update(Article).where(Article.id == article_id).values(views=Article.views + 1))
    db.commit()


def get_by_id(db: Session, article_id: int) -> Article | None:
    """管理端取单篇（含分类与标签关系）。"""
    return db.scalar(
        select(Article)
        .options(joinedload(Article.category), joinedload(Article.tags))
        .where(Article.id == article_id)
    )


def list_for_admin(
    db: Session,
    page: int,
    page_size: int,
    *,
    keyword: str | None = None,
    status: int | None = None,
    category_id: int | None = None,
) -> tuple[list[Article], int]:
    """管理端文章列表（含草稿），按更新时间倒序，返回 (列表, 总数)。"""
    stmt = (
        select(Article)
        .options(joinedload(Article.category), joinedload(Article.tags))
        .order_by(Article.updated_at.desc(), Article.id.desc())
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(Article.title.like(like))
    if status is not None:
        stmt = stmt.where(Article.status == status)
    if category_id is not None:
        stmt = stmt.where(Article.category_id == category_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return list(rows), total

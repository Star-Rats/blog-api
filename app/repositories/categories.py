"""分类数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Article, Category


def list_visible(db: Session) -> list[Category]:
    """前台可见的分类，按排序值升序。"""
    return list(
        db.scalars(
            select(Category)
            .where(Category.is_visible.is_(True))
            .order_by(Category.order_num.asc(), Category.id.asc())
        ).all()
    )


def published_counts(db: Session) -> dict[int, int]:
    """各分类下的已发布文章数，返回 {分类ID: 数量}。"""
    rows = db.execute(
        select(Article.category_id, func.count(Article.id))
        .where(Article.status == 1, Article.category_id.is_not(None))
        .group_by(Article.category_id)
    ).all()
    return {category_id: count for category_id, count in rows}


def list_with_article_count(db: Session) -> list[tuple[Category, int]]:
    """管理端：全部分类（含隐藏）及各自的文章总数。"""
    rows = db.execute(
        select(Category, func.count(Article.id))
        .outerjoin(Article, Article.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.order_num.asc(), Category.id.asc())
    ).all()
    return [(category, count or 0) for category, count in rows]


def count_articles(db: Session, category_id: int) -> int:
    return db.scalar(
        select(func.count(Article.id)).where(Article.category_id == category_id)
    ) or 0

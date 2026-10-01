"""公开接口：博客前台。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.time import to_iso
from app.db.base import get_db
from app.db.models import Article, Category, Tag
from app.schemas.blog import ArticleDetail, ArticleSummary, CategoryOut, Page, TagOut
from app.schemas.converters import article_summary, category_out

router = APIRouter(prefix="/api", tags=["public"])


def _published_stmt():
    return (
        select(Article)
        .options(joinedload(Article.category), joinedload(Article.tags))
        .where(Article.status == 1)
    )


def _category_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Article.category_id, func.count(Article.id))
        .where(Article.status == 1, Article.category_id.is_not(None))
        .group_by(Article.category_id)
    ).all()
    return {category_id: count for category_id, count in rows}


@router.get("/articles", response_model=Page)
def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    category_id: int | None = None,
    tag_id: int | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = _published_stmt()
    if category_id:
        stmt = stmt.where(Article.category_id == category_id)
    if tag_id:
        stmt = stmt.where(Article.tags.any(Tag.id == tag_id))
    if keyword:
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
    return Page(
        items=[article_summary(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/articles/archives")
def list_archives(db: Session = Depends(get_db)):
    """归档：全部已发布文章（含分类/标签），前端可按时间/分类/标签任意聚合。"""
    rows = db.scalars(
        _published_stmt().order_by(Article.published_at.desc(), Article.id.desc())
    ).unique().all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "slug": a.slug,
            "published_at": to_iso(a.published_at),
            "category_id": a.category_id,
            "category_name": a.category.name if a.category else None,
            "tags": [{"id": t.id, "name": t.name} for t in a.tags],
        }
        for a in rows
    ]


@router.get("/articles/{slug}", response_model=ArticleDetail)
def get_article(slug: str, db: Session = Depends(get_db)):
    article = db.scalar(_published_stmt().where(Article.slug == slug))
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    db.execute(
        update(Article).where(Article.id == article.id).values(views=Article.views + 1)
    )
    db.commit()
    db.refresh(article)
    summary = article_summary(article).model_dump()
    summary["body_html"] = article.body_html or ""
    return ArticleDetail(**summary)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    counts = _category_counts(db)
    categories = db.scalars(
        select(Category)
        .where(Category.is_visible.is_(True))
        .order_by(Category.order_num.asc(), Category.id.asc())
    ).all()
    return [category_out(c, counts.get(c.id, 0)) for c in categories]


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    """全部标签（按文章数倒序）。"""
    rows = db.execute(
        select(Tag, func.count(Article.id))
        .join(Article.tags)
        .where(Article.status == 1)
        .group_by(Tag.id)
        .order_by(func.count(Article.id).desc(), Tag.name.asc())
    ).all()
    return [TagOut(id=tag.id, name=tag.name) for tag, _count in rows]

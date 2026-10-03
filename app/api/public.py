"""公开接口：博客前台。参数校验与响应组装；数据访问在 repositories。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core import cache
from app.core.api_response import ApiResponse
from app.core.time import to_iso
from app.db.base import get_db
from app.repositories import articles as article_repo
from app.repositories import categories as category_repo
from app.repositories import tags as tag_repo
from app.schemas.blog import (
    ArticleArchiveItem,
    ArticleDetail,
    ArticleSummary,
    CategoryOut,
    Page,
    TagOut,
)
from app.schemas.converters import article_summary, category_out

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/articles", response_model=ApiResponse[Page])
def list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    category_id: int | None = None,
    tag_id: int | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
):
    rows, total = article_repo.list_published(
        db, page, page_size,
        category_id=category_id, tag_id=tag_id, keyword=keyword,
    )
    return ApiResponse.ok(Page(
        items=[article_summary(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    ))


@router.get("/articles/archives", response_model=ApiResponse[list[ArticleArchiveItem]])
def list_archives(db: Session = Depends(get_db)):
    """归档：全部已发布文章（含分类/标签），前端可按时间/分类/标签任意聚合。"""
    items = cache.get("archives")
    if items is None:
        items = [
            ArticleArchiveItem(
                id=a.id,
                title=a.title,
                slug=a.slug,
                published_at=to_iso(a.published_at),
                category_id=a.category_id,
                category_name=a.category.name if a.category else None,
                tags=[{"id": t.id, "name": t.name} for t in a.tags],
            ).model_dump()
            for a in article_repo.list_published_all(db)
        ]
        cache.set("archives", items)
    return ApiResponse.ok(items)


@router.get("/articles/{slug}", response_model=ApiResponse[ArticleDetail])
def get_article(slug: str, db: Session = Depends(get_db)):
    cached = cache.get(f"article:{slug}")
    if cached is not None:
        # 命中缓存：浏览量仍落库，页面展示的数字允许短暂滞后
        article_repo.increment_views(db, cached["id"])
        return ApiResponse.ok(ArticleDetail(**cached))

    article = article_repo.get_published_by_slug(db, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    article_repo.increment_views(db, article.id)
    db.refresh(article)
    detail = ArticleDetail(
        **article_summary(article).model_dump(),
        body_html=article.body_html or "",
    )
    cache.set(f"article:{slug}", detail.model_dump())
    return ApiResponse.ok(detail)


@router.get("/categories", response_model=ApiResponse[list[CategoryOut]])
def list_categories(db: Session = Depends(get_db)):
    categories = cache.get("categories")
    if categories is None:
        counts = category_repo.published_counts(db)
        categories = [category_out(c, counts.get(c.id, 0)).model_dump() for c in category_repo.list_visible(db)]
        cache.set("categories", categories)
    return ApiResponse.ok([CategoryOut(**c) for c in categories])


@router.get("/tags", response_model=ApiResponse[list[TagOut]])
def list_tags(db: Session = Depends(get_db)):
    """全部标签（按文章数倒序）。"""
    tags = cache.get("tags")
    if tags is None:
        tags = [tag.model_dump() for tag in (TagOut(id=t.id, name=t.name) for t, _count in tag_repo.list_with_published_count(db))]
        cache.set("tags", tags)
    return ApiResponse.ok([TagOut(**t) for t in tags])

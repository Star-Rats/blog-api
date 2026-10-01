"""首页聚合接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Article, Category, Tag
from app.schemas.blog import AboutOut, HomeOut, HomeStats, TagOut
from app.schemas.converters import article_summary, category_out
from app.services.settings import get_site_settings

from app.api.public import _category_counts, _published_stmt

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/about", response_model=AboutOut)
def get_about(db: Session = Depends(get_db)):
    """「关于我」页内容（Markdown，后台站点设置中维护）。"""
    return AboutOut(content=get_site_settings(db).get("about_content", ""))


@router.get("/home", response_model=HomeOut)
def get_home(db: Session = Depends(get_db)):
    counts = _category_counts(db)
    article_count = sum(counts.values())
    category_rows = db.scalars(
        select(Category)
        .where(Category.is_visible.is_(True))
        .order_by(Category.order_num.asc(), Category.id.asc())
    ).all()
    tag_rows = db.execute(
        select(Tag, func.count(Article.id))
        .join(Article.tags)
        .where(Article.status == 1)
        .group_by(Tag.id)
        .order_by(func.count(Article.id).desc())
        .limit(20)
    ).all()
    recent = db.scalars(
        _published_stmt().order_by(Article.published_at.desc(), Article.id.desc()).limit(6)
    ).unique().all()
    return HomeOut(
        site=get_site_settings(db),
        stats=HomeStats(
            article_count=article_count,
            category_count=len(category_rows),
            tag_count=len(tag_rows),
        ),
        recent_articles=[article_summary(a) for a in recent],
        categories=[category_out(c, counts.get(c.id, 0)) for c in category_rows],
        tags=[TagOut(id=t.id, name=t.name) for t, _count in tag_rows],
    )

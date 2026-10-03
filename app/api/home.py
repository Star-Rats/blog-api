"""首页聚合与「关于」接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import cache
from app.core.api_response import ApiResponse
from app.db.base import get_db
from app.repositories import articles as article_repo
from app.repositories import categories as category_repo
from app.repositories import tags as tag_repo
from app.schemas.blog import AboutOut, HomeOut, HomeStats, TagOut
from app.schemas.converters import article_summary, category_out
from app.services.settings import get_site_settings

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/about", response_model=ApiResponse[AboutOut])
def get_about(db: Session = Depends(get_db)):
    """「关于我」页内容（Markdown，后台站点设置中维护）。"""
    content = get_site_settings(db).get("about_content", "")
    return ApiResponse.ok(AboutOut(content=content))


@router.get("/home", response_model=ApiResponse[HomeOut])
def get_home(db: Session = Depends(get_db)):
    home = cache.get("home")
    if home is None:
        counts = category_repo.published_counts(db)
        visible_categories = category_repo.list_visible(db)
        tag_rows = tag_repo.list_with_published_count(db, limit=20)
        recent = article_repo.recent_published(db, 6)
        home = HomeOut(
            site=get_site_settings(db),
            stats=HomeStats(
                article_count=article_repo.count_published(db),
                category_count=len(visible_categories),
                tag_count=len(tag_rows),
            ),
            recent_articles=[article_summary(a) for a in recent],
            categories=[category_out(c, counts.get(c.id, 0)) for c in visible_categories],
            tags=[TagOut(id=t.id, name=t.name) for t, _count in tag_rows],
        ).model_dump()
        cache.set("home", home)
    return ApiResponse.ok(HomeOut(**home))

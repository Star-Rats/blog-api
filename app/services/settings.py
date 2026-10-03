"""设置存储：站点设置与语雀配置（Token / 知识库链接），key-value 存数据库，admin 可改。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import Settings, get_settings
from app.db.models import Setting

# 站点设置可编辑键（about_content 为「关于我」页的 Markdown 内容）
EDITABLE_KEYS = ("site_title", "site_description", "site_footer", "about_content")

def get_setting(db: Session, key: str) -> str | None:
    row = db.scalar(select(Setting).where(Setting.key == key))
    return row.value if row else None


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.scalar(select(Setting).where(Setting.key == key))
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


# ---- 站点设置 ----


def get_site_settings(db: Session, settings: Settings | None = None) -> dict[str, str]:
    cached = cache.get("site_settings")
    if cached is not None:
        return cached
    settings = settings or get_settings()
    result: dict[str, str] = {
        "site_title": settings.site_title,
        "site_description": settings.site_description,
        "site_footer": "",
        "about_content": "",
    }
    for row in db.scalars(select(Setting).where(Setting.key.in_(EDITABLE_KEYS))):
        if row.value:
            result[row.key] = row.value
    cache.set("site_settings", result)
    return result


def update_site_settings(db: Session, data: dict[str, str]) -> None:
    for key in EDITABLE_KEYS:
        if data.get(key) is None:
            continue
        set_setting(db, key, str(data[key]))
    db.commit()
    cache.bump()

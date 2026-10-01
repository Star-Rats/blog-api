"""文章管理服务：后台创作、发布、删除，slug/摘要/字数/封面的派生逻辑。"""
from __future__ import annotations

import html as html_lib
import re
import secrets
import string

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BizError
from app.core.time import utcnow
from app.db.models import Article

_ALPHABET = string.ascii_lowercase + string.digits
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
_TAG_STRIP = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    """HTML 转纯文本，用于搜索与摘要。"""
    text = _TAG_STRIP.sub(" ", html or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def generate_slug(db: Session, desired: str | None) -> str:
    """slug：优先用自定义值，否则生成 8 位随机串（语雀风格）；冲突自动加后缀。"""
    base = (desired or "").strip().lower()
    if base:
        if not _SLUG_RE.match(base):
            raise BizError("slug 只能包含小写字母、数字和连字符")
    else:
        base = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    slug = base
    seq = 2
    while db.scalar(select(Article.id).where(Article.slug == slug)) is not None:
        slug = f"{base}-{seq}"
        seq += 1
    return slug


def derive_fields(article: Article) -> None:
    """从正文派生：纯文本、摘要、字数；封面缺省时取正文第一张图。"""
    article.body_text = html_to_text(article.body_html or "")
    if not (article.description or "").strip():
        article.description = article.body_text[:120]
    text = re.sub(r"<[^>]+>", "", article.body_html or "")
    article.word_count = len(re.sub(r"\s", "", text))
    if not (article.cover or "").strip():
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', article.body_html or "")
        article.cover = match.group(1) if match else None


def create_article(db: Session, data: dict) -> Article:
    title = (data.get("title") or "").strip()
    if not title:
        raise BizError("标题不能为空")
    article = Article(
        slug=generate_slug(db, data.get("slug")),
        title=title,
        description=data.get("description") or "",
        cover=data.get("cover") or None,
        body_html=data.get("body_html") or "",
        status=int(data.get("status") or 0),
        category_id=data.get("category_id"),
    )
    derive_fields(article)
    if article.status == 1 and article.published_at is None:
        article.published_at = utcnow()
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def update_article(db: Session, article: Article, data: dict) -> Article:
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise BizError("标题不能为空")
        article.title = title
    if "slug" in data and data["slug"] and data["slug"] != article.slug:
        article.slug = generate_slug(db, data["slug"])
    for field in ("body_html",):
        if field in data and data[field] is not None:
            setattr(article, field, data[field])
    # 摘要/封面显式传空 = 重新自动派生（摘要取正文前 120 字、封面取正文第一张图）
    if "description" in data:
        article.description = data.get("description") or ""
    if "cover" in data:
        article.cover = data.get("cover") or None
    if "category_id" in data:
        article.category_id = data["category_id"]
    if "status" in data and data["status"] is not None:
        new_status = int(data["status"])
        if new_status == 1 and article.status == 0 and article.published_at is None:
            article.published_at = utcnow()  # 首次发布记录时间
        article.status = new_status
    derive_fields(article)
    db.commit()
    db.refresh(article)
    return article


def delete_article(db: Session, article: Article) -> None:
    db.delete(article)
    db.commit()


def count_articles(db: Session, published_only: bool = False) -> int:
    stmt = select(func.count(Article.id))
    if published_only:
        stmt = stmt.where(Article.status == 1)
    return db.scalar(stmt) or 0

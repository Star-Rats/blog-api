"""分类与标签的博客侧维护逻辑（admin CRUD、文章指派、slug 生成）。"""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BizError
from app.db.models import Article, ArticleTag, Category, Tag


def auto_slug(name: str) -> str:
    """由名称生成 URL slug：小写、空格转连字符，保留中英文/数字/连字符。"""
    slug = re.sub(r"\s+", "-", name.strip().lower())
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "", slug)
    return slug.strip("-") or "item"


def _unique_slug(db: Session, model: type[Category], desired: str, exclude_id: int | None = None) -> str:
    base = desired
    slug = base
    seq = 2
    while True:
        stmt = select(model.id).where(model.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)
        if db.scalar(stmt) is None:
            return slug
        slug = f"{base}-{seq}"
        seq += 1


# ---- 分类 ----


def create_category(db: Session, name: str, slug: str | None = None, **extra) -> Category:
    name = name.strip()
    if not name:
        raise BizError("分类名称不能为空")
    if db.scalar(select(Category.id).where(Category.name == name)):
        raise BizError(f"分类「{name}」已存在")
    category = Category(
        name=name,
        slug=_unique_slug(db, Category, slug.strip() if slug and slug.strip() else auto_slug(name)),
        description=extra.get("description"),
        cover=extra.get("cover"),
        order_num=extra.get("order_num") or 0,
        is_visible=extra.get("is_visible", True),
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, category_id: int, data: dict) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise BizError("分类不存在", 404)
    if "name" in data and data["name"]:
        name = str(data["name"]).strip()
        exists = db.scalar(
            select(Category.id).where(Category.name == name, Category.id != category_id)
        )
        if exists:
            raise BizError(f"分类「{name}」已存在")
        category.name = name
    if "slug" in data and data["slug"]:
        category.slug = _unique_slug(db, Category, str(data["slug"]).strip(), exclude_id=category_id)
    for field in ("description", "cover"):
        if field in data:
            setattr(category, field, data[field])
    if "order_num" in data and data["order_num"] is not None:
        category.order_num = int(data["order_num"])
    if "is_visible" in data and data["is_visible"] is not None:
        category.is_visible = bool(data["is_visible"])
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int) -> None:
    category = db.get(Category, category_id)
    if category is None:
        raise BizError("分类不存在", 404)
    count = db.scalar(select(func.count(Article.id)).where(Article.category_id == category_id)) or 0
    if count:
        raise BizError(f"该分类下还有 {count} 篇文章，请先在文章管理中移出")
    db.delete(category)
    db.commit()


# ---- 标签 ----


def create_tag(db: Session, name: str) -> Tag:
    name = name.strip()
    if not name:
        raise BizError("标签名称不能为空")
    if db.scalar(select(Tag.id).where(Tag.name == name)):
        raise BizError(f"标签「{name}」已存在")
    tag = Tag(name=name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def rename_tag(db: Session, tag_id: int, name: str) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise BizError("标签不存在", 404)
    name = name.strip()
    if not name:
        raise BizError("标签名称不能为空")
    exists = db.scalar(select(Tag.id).where(Tag.name == name, Tag.id != tag_id))
    if exists:
        raise BizError(f"标签「{name}」已存在")
    tag.name = name
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag_id: int) -> None:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise BizError("标签不存在", 404)
    db.query(ArticleTag).filter(ArticleTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()


def set_article_tags(db: Session, article: Article, names: list[str]) -> None:
    """全量设置文章标签（以传入为准，多退少补；标签不存在则自动创建）。"""
    target_tags: list[Tag] = []
    for name in dict.fromkeys(n.strip() for n in names if n and n.strip()):
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        target_tags.append(tag)
    target_ids = {tag.id for tag in target_tags}
    current_ids = {tag.id for tag in article.tags}

    for tag_id in current_ids - target_ids:
        link = db.scalar(
            select(ArticleTag).where(
                ArticleTag.article_id == article.id, ArticleTag.tag_id == tag_id
            )
        )
        if link is not None:
            db.delete(link)
    for tag_id in target_ids - current_ids:
        db.add(ArticleTag(article_id=article.id, tag_id=tag_id))
    db.commit()


def set_article_category(db: Session, article: Article, category_id: int | None) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise BizError("分类不存在")
    article.category_id = category_id
    db.commit()

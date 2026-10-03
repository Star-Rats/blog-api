"""把 ORM 对象转成响应 schema 的辅助函数。"""
from app.core.time import to_iso
from app.db.models import Article, Category, Tag
from app.schemas.blog import (
    AdminArticleOut,
    ArticleSummary,
    CategoryOut,
    TagOut,
)


def tag_out(tag: Tag) -> TagOut:
    return TagOut(id=tag.id, name=tag.name)


def article_summary(article: Article) -> ArticleSummary:
    category = article.category
    return ArticleSummary(
        id=article.id,
        slug=article.slug,
        title=article.title,
        description=article.description,
        cover=article.cover,
        category_id=article.category_id,
        category_name=category.name if category else None,
        tags=[tag_out(tag) for tag in article.tags],
        views=article.views,
        word_count=article.word_count,
        status=article.status,
        published_at=to_iso(article.published_at),
        updated_at=to_iso(article.gmt_modify),
    )


def category_out(category: Category, article_count: int) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        cover=category.cover,
        order_num=category.order_num,
        is_visible=category.is_visible,
        article_count=article_count,
    )


def admin_article_out(article: Article) -> AdminArticleOut:
    return AdminArticleOut(
        id=article.id,
        slug=article.slug,
        title=article.title,
        description=article.description,
        cover=article.cover,
        status=article.status,
        category_id=article.category_id,
        category_name=article.category.name if article.category else None,
        tags=[tag_out(tag) for tag in article.tags],
        views=article.views,
        word_count=article.word_count,
        created_at=to_iso(article.gmt_create),
        updated_at=to_iso(article.gmt_modify),
        published_at=to_iso(article.published_at),
    )

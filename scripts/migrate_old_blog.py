"""一次性迁移脚本：把旧博客（new-blog/minzheng，表前缀 tb_*）的文章迁到新库。

- 仅迁移未删除的文章；status 映射：1公开→已发布，2私密/3草稿→草稿
- 发布时间（create_time）原样保留到 gmt_create / published_at；update_time → gmt_modify
- 正文 markdown → HTML（markdown-it，启用表格/删除线），图片 URL 不改动
- 标签一并迁移并保留关联；分类按名称映射到新库已有分类（未匹配的文章归未分类，后台可手动调整）
- slug 规则：article-{旧文档ID}（稳定，可回溯）
- 幂等：slug 已存在则跳过

用法（在 api 容器内或本地，连接新库）：
    OLD_DB_URL=mysql+pymysql://root:密码@127.0.0.1:3306/旧库名 \\
    .venv/bin/python scripts/migrate_old_blog.py

新库连接复用 .env 的 DB_* 配置。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

import httpx  # noqa: F401  确保 httpx 已装
from markdown_it import MarkdownIt
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import get_settings
from app.db.models import Article, ArticleTag, Category, Tag
from app.services.articles import derive_fields  # 摘要/字数/封面兜底
from app.services.taxonomy import auto_slug

_md = MarkdownIt("commonmark").enable(["table", "strikethrough"])


def old_engine():
    url = os.getenv("OLD_DB_URL", "")
    if not url:
        print("请通过 OLD_DB_URL 提供旧库连接，如 mysql+pymysql://root:密码@127.0.0.1:3306/old_blog")
        sys.exit(1)
    return create_engine(url)


def fetch_old(engine) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """返回 (articles, categories, tags, article_tags)。"""
    with engine.connect() as conn:
        articles = [
            dict(row._mapping)
            for row in conn.execute(text(
                "SELECT id, category_id, article_cover, article_title, article_content,"
                " original_url, is_delete, status, create_time, update_time"
                " FROM tb_article"
            ))
        ]
        categories = [dict(row._mapping) for row in conn.execute(
            text("SELECT id, category_name FROM tb_category"))]
        tags = [dict(row._mapping) for row in conn.execute(
            text("SELECT id, tag_name FROM tb_tag"))]
        article_tags = [dict(row._mapping) for row in conn.execute(
            text("SELECT article_id, tag_id FROM tb_article_tag"))]
    return articles, categories, tags, article_tags


def main() -> None:
    old = old_engine()
    articles, categories, tags, article_tags = fetch_old(old)

    from app.db.base import SessionLocal

    db = SessionLocal()

    published = 0
    skipped = 0

    # 1) 分类：旧分类按名称映射到新库已有分类（新博客的分类体系由博主自定，不自动创建）
    existing_cats = {c.name: c for c in db.scalars(select(Category)).all()}
    old_cat_to_new: dict[int, Category] = {}
    unmapped: set[str] = set()
    for cat in categories:
        name = str(cat["category_name"]).strip()
        if name in existing_cats:
            old_cat_to_new[cat["id"]] = existing_cats[name]
        else:
            unmapped.add(name)

    # 2) 标签：旧 id -> 新 Tag
    old_tag_to_new: dict[int, Tag] = {}
    for tag in tags:
        name = str(tag["tag_name"]).strip()
        exists = db.scalar(select(Tag).where(Tag.name == name))
        if exists:
            old_tag_to_new[tag["id"]] = exists
            continue
        new_tag = Tag(name=name)
        db.add(new_tag)
        db.flush()
        old_tag_to_new[tag["id"]] = new_tag

    # 3) 文章（跳过已删除）
    for old in articles:
        if int(old["is_delete"] or 0):
            continue
        slug = f"article-{old['id']}"
        if db.scalar(select(Article.id).where(Article.slug == slug)):
            skipped += 1
            continue
        status_old = int(old["status"] or 0)
        body_html = _md.render(old["article_content"] or "")

        article = Article(
            slug=slug,
            title=str(old["article_title"] or "").strip() or f"文章 {old['id']}",
            body_html=body_html,
            cover=old["article_cover"] or None,
            status=1 if status_old == 1 else 0,  # 1公开→已发布；2私密/3草稿→草稿
            published_at=old["create_time"] if status_old == 1 else None,
            gmt_create=old["create_time"],
            gmt_modify=old["update_time"] or old["create_time"],
        )
        if old["category_id"] and old["category_id"] in old_cat_to_new:
            article.category_id = old_cat_to_new[old["category_id"]].id
        derive_fields(article)  # 摘要/字数/封面兜底（图片 URL 不改动）
        db.add(article)
        db.flush()
        for tag_id in [
            at["tag_id"] for at in article_tags if at["article_id"] == old["id"]
        ]:
            if tag_id in old_tag_to_new:
                db.add(ArticleTag(article_id=article.id, tag_id=old_tag_to_new[tag_id].id))
        published += 1

    db.commit()
    cache.bump()

    deleted = sum(1 for a in articles if int(a["is_delete"] or 0))
    print(f"迁移完成：旧库文章 {len(articles)} 篇（已删除跳过 {deleted}），导入 {published}，跳过(已存在) {skipped}")
    print(f"映射分类 {len(old_cat_to_new)} 个，标签 {len(old_tag_to_new)} 个")
    if unmapped:
        print("以下旧分类在新库不存在，对应文章为未分类（可后台手动调整）:", "、".join(sorted(unmapped)))


if __name__ == "__main__":
    main()

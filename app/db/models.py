"""数据模型：文章在管理后台本地创作与发布，分类/标签由博客自身维护。"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.time import utcnow
from app.db.base import Base


class LongText(TypeDecorator):
    """TEXT，在 MySQL 下使用 LONGTEXT（正文含图片时可能很大）。"""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "mysql":
            return dialect.type_descriptor(LONGTEXT())
        return super().load_dialect_impl(dialect)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # URL 标识，创建时可省略（由名称自动生成）
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    cover: Mapped[str | None] = mapped_column(String(1024))
    order_num: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    gmt_create: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    gmt_modify: Mapped[datetime | None] = mapped_column(DateTime, onupdate=utcnow)

    articles: Mapped[list["Article"]] = relationship(back_populates="category")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 博客自身维护的分类，可为空（未分类）
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    # URL 标识，创建时自动生成随机 slug，也可自定义
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(500), default="")
    cover: Mapped[str | None] = mapped_column(String(1024))
    # 编辑器产出的 HTML 正文
    body_html: Mapped[str] = mapped_column(LongText, default="")
    # 纯文本正文，用于搜索与摘要
    body_text: Mapped[str] = mapped_column(LongText, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    # 0 草稿 1 已发布；草稿不出现在前台
    status: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # 发布时间：首次发布时写入
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # 本站浏览量
    views: Mapped[int] = mapped_column(Integer, default=0)
    gmt_create: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    gmt_modify: Mapped[datetime | None] = mapped_column(DateTime, onupdate=utcnow)

    category: Mapped["Category"] = relationship(back_populates="articles")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="article_tags", back_populates="articles", lazy="selectin"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    gmt_create: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    articles: Mapped[list["Article"]] = relationship(
        secondary="article_tags", back_populates="tags"
    )


class ArticleTag(Base):
    __tablename__ = "article_tags"
    __table_args__ = (UniqueConstraint("article_id", "tag_id", name="uq_article_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), index=True
    )


class Setting(Base):
    """站点设置，key-value 存储，管理端可改。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    gmt_modify: Mapped[datetime | None] = mapped_column(DateTime, onupdate=utcnow)

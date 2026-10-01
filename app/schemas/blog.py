"""Pydantic 请求/响应模型。"""
from pydantic import BaseModel, Field


class TagOut(BaseModel):
    id: int
    name: str


class ArticleSummary(BaseModel):
    """文章列表项（不含正文）。"""

    id: int
    slug: str
    title: str
    description: str
    cover: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    tags: list[TagOut] = []
    views: int
    word_count: int
    status: int
    published_at: str | None = None
    updated_at: str | None = None


class ArticleDetail(ArticleSummary):
    body_html: str


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    cover: str | None = None
    order_num: int
    is_visible: bool
    article_count: int


class HomeStats(BaseModel):
    article_count: int
    category_count: int
    tag_count: int


class HomeOut(BaseModel):
    site: dict
    stats: HomeStats
    recent_articles: list[ArticleSummary]
    categories: list[CategoryOut]
    tags: list[TagOut]


class AboutOut(BaseModel):
    content: str


class AdminArticleOut(BaseModel):
    """管理端文章项。"""

    id: int
    slug: str
    title: str
    description: str
    cover: str | None = None
    status: int
    category_id: int | None = None
    category_name: str | None = None
    tags: list[TagOut] = []
    views: int
    word_count: int
    created_at: str | None = None
    updated_at: str | None = None
    published_at: str | None = None


class AdminArticleDetailOut(AdminArticleOut):
    """编辑器加载用：含正文 HTML。"""

    body_html: str


# ---- 管理端请求体 ----


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SettingsUpdateRequest(BaseModel):
    site_title: str | None = None
    site_description: str | None = None
    site_footer: str | None = None
    about_content: str | None = None


class CategoryIn(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    cover: str | None = None
    order_num: int = 0
    is_visible: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    cover: str | None = None
    order_num: int | None = None
    is_visible: bool | None = None


class TagIn(BaseModel):
    name: str


class ArticleIn(BaseModel):
    """创建/编辑文章；status: 0 草稿 1 发布。"""

    title: str
    slug: str | None = Field(None, description="留空自动生成随机 slug")
    body_html: str = ""
    description: str | None = None
    cover: str | None = None
    status: int = Field(0, ge=0, le=1)
    category_id: int | None = None
    tags: list[str] | None = Field(None, description="全量设置；不传则不改动")


class ArticleUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    body_html: str | None = None
    description: str | None = None
    cover: str | None = None
    status: int | None = Field(None, ge=0, le=1)
    category_id: int | None = None
    tags: list[str] | None = None

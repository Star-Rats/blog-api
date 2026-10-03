"""管理端接口：登录、文章创作管理、分类/标签维护、图片上传（OSS）、站点设置。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import BizError
from app.core.security import create_access_token, get_current_admin
from app.db.base import get_db
from app.repositories import articles as article_repo
from app.repositories import categories as category_repo
from app.repositories import tags as tag_repo
from app.schemas.blog import (
    AdminArticleDetailOut,
    AdminArticleOut,
    ArticleIn,
    ArticleUpdate,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    LoginRequest,
    LoginResponse,
    Page,
    SettingsUpdateRequest,
    TagIn,
    TagOut,
)
from app.schemas.converters import admin_article_out, category_out, tag_out
from app.services import articles as article_service
from app.services import oss as oss_service
from app.services import yuque_import
from app.services import taxonomy
from app.services.settings import get_site_settings, update_site_settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---- 登录 ----


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, settings: Settings = Depends(get_settings)):
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return LoginResponse(access_token=create_access_token(body.username, settings))


# ---- 文章管理 ----


@router.get("/articles", response_model=Page)
def list_admin_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    status: int | None = Query(None, ge=0, le=1, description="0 草稿 / 1 已发布"),
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    rows, total = article_repo.list_for_admin(
        db, page, page_size, keyword=keyword, status=status, category_id=category_id,
    )
    return Page(
        items=[admin_article_out(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/articles/{article_id}", response_model=AdminArticleDetailOut)
def get_admin_article(
    article_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """单篇文章详情（含 body_html，供编辑器加载）。"""
    article = article_repo.get_by_id(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    out = admin_article_out(article).model_dump()
    out["body_html"] = article.body_html or ""
    return AdminArticleDetailOut(**out)


@router.post("/articles", response_model=AdminArticleOut)
def create_article(
    body: ArticleIn,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    article = article_service.create_article(db, body.model_dump())
    if body.tags is not None:
        taxonomy.set_article_tags(db, article, body.tags)
    db.refresh(article)
    return admin_article_out(article)


@router.put("/articles/{article_id}", response_model=AdminArticleOut)
def update_article(
    article_id: int,
    body: ArticleUpdate,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    article = article_repo.get_by_id(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    # 只处理请求里显式给出的字段（显式传 null 分类表示清除）
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data:
        taxonomy.set_article_category(db, article, data.pop("category_id"))
    if "tags" in data:
        taxonomy.set_article_tags(db, article, data.pop("tags"))
    article_service.update_article(db, article, data)
    db.refresh(article)
    return admin_article_out(article)


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    article = article_repo.get_by_id(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    article_service.delete_article(db, article)
    return {"status": "deleted"}


@router.post("/articles/import", response_model=AdminArticleDetailOut)
def import_yuque_article(
    body: dict,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """按公开语雀文档链接导入为可编辑草稿。"""
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="请提供语雀文档链接")
    article = yuque_import.import_from_yuque(db, url)
    out = admin_article_out(article).model_dump()
    out["body_html"] = article.body_html or ""
    return AdminArticleDetailOut(**out)


# ---- 分类维护 ----


@router.get("/categories", response_model=list[CategoryOut])
def list_admin_categories(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """全部分类（含隐藏），带文章数。"""
    return [category_out(category, count) for category, count in category_repo.list_with_article_count(db)]


@router.post("/categories", response_model=CategoryOut)
def create_category(
    body: CategoryIn,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    category = taxonomy.create_category(
        db,
        body.name,
        slug=body.slug,
        description=body.description,
        cover=body.cover,
        order_num=body.order_num,
        is_visible=body.is_visible,
    )
    return category_out(category, 0)


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    category = taxonomy.update_category(db, category_id, body.model_dump(exclude_none=True))
    return category_out(category, category_repo.count_articles(db, category_id))


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    taxonomy.delete_category(db, category_id)
    return {"status": "deleted"}


# ---- 标签维护 ----


@router.get("/tags", response_model=list[TagOut])
def list_admin_tags(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    return [tag_out(tag) for tag in tag_repo.list_all(db)]


@router.post("/tags", response_model=TagOut)
def create_tag(
    body: TagIn,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    return tag_out(taxonomy.create_tag(db, body.name))


@router.put("/tags/{tag_id}", response_model=TagOut)
def rename_tag(
    tag_id: int,
    body: TagIn,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    return tag_out(taxonomy.rename_tag(db, tag_id, body.name))


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    taxonomy.delete_tag(db, tag_id)
    return {"status": "deleted"}


# ---- 图片上传（阿里云 OSS） ----


def _oss_config_view(db: Session) -> dict:
    config = oss_service.get_oss_config(db)
    return {
        "endpoint": config["oss_endpoint"],
        "access_key_id": config["oss_access_key_id"],
        "access_key_secret_masked": oss_service.mask_secret(config["oss_access_key_secret"]),
        "bucket": config["oss_bucket"],
        "custom_domain": config["oss_custom_domain"],
        "configured": bool(
            config["oss_endpoint"] and config["oss_access_key_id"]
            and config["oss_access_key_secret"] and config["oss_bucket"]
        ),
    }


@router.get("/oss/config")
def read_oss_config(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    return _oss_config_view(db)


@router.put("/oss/config")
def write_oss_config(
    body: dict,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """secret 留空表示保持不变。"""
    data = {f"oss_{k}": v for k, v in body.items() if k in ("endpoint", "bucket", "custom_domain")}
    if body.get("access_key_id"):
        data["oss_access_key_id"] = body["access_key_id"]
    if body.get("access_key_secret"):
        data["oss_access_key_secret"] = body["access_key_secret"]
    oss_service.set_oss_config(db, data)
    return _oss_config_view(db)


@router.post("/oss/test")
def test_oss(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    return oss_service.test_oss(db)


@router.post("/images")
def upload_image(
    file: UploadFile,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """编辑器图片上传；返回 wangEditor 约定的 {errno, data:{url}} 结构。"""
    data = file.file.read()
    url = oss_service.upload_image(db, file.filename or "img", file.content_type or "", data)
    return {"errno": 0, "data": {"url": url, "alt": file.filename or "", "href": url}}


# ---- 站点设置 ----


@router.get("/settings")
def read_settings(
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    return get_site_settings(db)


@router.put("/settings")
def write_settings(
    body: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    update_site_settings(db, body.model_dump(exclude_none=True))
    return get_site_settings(db)

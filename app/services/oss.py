"""图片上传到阿里云 OSS；OSS 配置存 settings 表（管理后台可改）。"""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime

import oss2
from sqlalchemy.orm import Session

from app.core.errors import BizError
from app.services.settings import get_setting, set_setting

# 允许的图片类型与大小上限
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 10 * 1024 * 1024
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

OSS_KEYS = ("oss_endpoint", "oss_access_key_id", "oss_access_key_secret", "oss_bucket", "oss_custom_domain")


def get_oss_config(db: Session) -> dict[str, str]:
    return {key: get_setting(db, key) or "" for key in OSS_KEYS}


def set_oss_config(db: Session, data: dict[str, str]) -> None:
    for key in OSS_KEYS:
        if key in data and data[key] is not None:
            set_setting(db, key, str(data[key]).strip())
    db.commit()


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}***{secret[-4:]}"


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint:
        raise BizError("OSS Endpoint 未配置")
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint


def public_url(config: dict[str, str], key: str) -> str:
    domain = (config.get("oss_custom_domain") or "").strip().rstrip("/")
    if domain:
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        return f"{domain}/{key}"
    endpoint = _normalize_endpoint(config["oss_endpoint"]).removeprefix("https://").removeprefix("http://")
    return f"https://{config['oss_bucket']}.{endpoint}/{key}"


def _bucket(db: Session) -> tuple[oss2.Bucket, dict[str, str]]:
    config = get_oss_config(db)
    missing = [k.removeprefix("oss_") for k in ("oss_endpoint", "oss_access_key_id", "oss_access_key_secret", "oss_bucket") if not config.get(k)]
    if missing:
        raise BizError(f"OSS 配置不完整，请在站点设置中补充：{', '.join(missing)}")
    auth = oss2.Auth(config["oss_access_key_id"], config["oss_access_key_secret"])
    bucket = oss2.Bucket(auth, _normalize_endpoint(config["oss_endpoint"]), config["oss_bucket"])
    return bucket, config


def test_oss(db: Session) -> dict:
    """校验配置与凭证：读取 Bucket 信息。"""
    bucket, config = _bucket(db)
    try:
        info = bucket.get_bucket_info()
    except oss2.exceptions.OssError as e:
        raise BizError(f"OSS 连接失败：{e.message or e.status}（请检查密钥、Bucket 与 Endpoint 是否匹配）")
    return {"ok": True, "bucket": config["oss_bucket"], "region": info.location}


def upload_image(db: Session, filename: str, content_type: str, data: bytes) -> str:
    """上传图片，返回可直接访问的 URL。"""
    if content_type not in ALLOWED_TYPES:
        raise BizError("仅支持 jpg / png / gif / webp / svg 图片")
    if len(data) > MAX_SIZE:
        raise BizError("图片不能超过 10MB")

    bucket, config = _bucket(db)
    ext = _EXT_BY_TYPE.get(content_type, ".png")
    safe_name = re.sub(r"[^0-9a-zA-Z]+", "-", filename.rsplit(".", 1)[0])[:20].strip("-")
    name = f"{datetime.utcnow():%Y%m}/{safe_name or 'img'}-{secrets.token_hex(4)}{ext}"
    key = f"blog/{name}"
    try:
        bucket.put_object(key, data, headers={"Content-Type": content_type})
    except oss2.exceptions.OssError as e:
        raise BizError(f"OSS 上传失败：{e.message or e.status}（请检查密钥与 Bucket 配置）")
    return public_url(config, key)

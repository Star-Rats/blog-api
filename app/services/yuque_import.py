"""按公开链接导入单篇语雀文档为可编辑草稿。

利用语雀对公开文档开放的 /markdown 导出端点（无需 Token）：
    https://www.yuque.com/{user}/{book}/{slug}/markdown?plain=true
私有文档无法通过该方式获取，会返回明确错误。

若后台已配置阿里云 OSS，导入时自动把正文中的语雀图片转存到 OSS 并替换 URL；
未配置 OSS 时保留原始图片链接（主站已有 no-referrer 处理防盗链）。
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime

import httpx
from markdown_it import MarkdownIt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BizError
from app.services import oss as oss_service
from app.services.articles import create_article

_URL_RE = re.compile(
    r"^https?://[^/]+/(?P<user>[A-Za-z0-9_-]+)/(?P<book>[A-Za-z0-9_-]+)/(?P<slug>[A-Za-z0-9._-]+?)(?:/markdown)?/?(\?.*)?$"
)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$")
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

_markdown = MarkdownIt("commonmark").enable(["table", "strikethrough"])


def parse_yuque_url(url: str) -> tuple[str, str]:
    """从链接中提取 namespace（user/book）与文档 slug。"""
    url = (url or "").strip()
    match = _URL_RE.match(url)
    if not match:
        raise BizError("请粘贴公开语雀文档链接，形如 https://www.yuque.com/用户名/知识库/文档slug")
    return f"{match.group('user')}/{match.group('book')}", match.group("slug")


def _get(client: httpx.Client, url: str) -> httpx.Response:
    try:
        resp = client.get(url, follow_redirects=True)
    except httpx.HTTPError:
        raise BizError("无法访问语雀，请稍后重试")
    if resp.status_code != 200:
        raise BizError("导入失败：该链接不是公开的语雀文档（或已失效/被删除）")
    return resp


def fetch_markdown(namespace: str, slug: str) -> str:
    base = get_settings().yuque_import_base.rstrip("/")
    resp = _get(
        httpx.Client(headers={"User-Agent": _UA}, timeout=20),
        f"{base}/{namespace}/{slug}/markdown?plain=true&linebreak=false",
    )
    return resp.text


def fetch_page_title(namespace: str, slug: str) -> str | None:
    """文档页 <title>，形如「文档标题 · 语雀」。"""
    base = get_settings().yuque_import_base.rstrip("/")
    resp = _get(httpx.Client(headers={"User-Agent": _UA}, timeout=20), f"{base}/{namespace}/{slug}")
    match = _TITLE_TAG_RE.search(resp.text)
    if not match:
        return None
    title = match.group(1).strip()
    return re.sub(r"\s*·\s*语雀\s*$", "", title) or None


def _split_title(markdown: str) -> tuple[str | None, str]:
    """正文首行若为一级标题则作为文档标题并从正文移除。"""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        match = _H1_RE.match(line.strip())
        if match:
            rest = "\n".join(lines[index + 1 :]).lstrip("\n")
            return match.group(1).strip(), rest
        break  # 首个非空行不是标题
    return None, markdown


# 语雀图片 CDN（含公式图 cdn.nlark.com / 附件图片 cdn.yuque.com 等）
_IMG_RE = re.compile(r'<img\s[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)
_SKIP_SRC_RE = re.compile(r"^(data:|blob:)", re.IGNORECASE)


def _oss_ready(db: Session) -> bool:
    config = oss_service.get_oss_config(db)
    return bool(
        config["oss_endpoint"] and config["oss_access_key_id"]
        and config["oss_access_key_secret"] and config["oss_bucket"]
    )


def _guess_content_type(url: str, resp: httpx.Response) -> str:
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype.startswith("image/"):
        return ctype
    ext = url.rsplit(".", 1)[-1].lower()
    return {  # 语雀图片 URL 常带查询参数且无扩展名，按扩展名兜底
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp", "svg": "image/svg+xml",
    }.get(ext, "image/png")


def transfer_images_to_oss(db: Session, html: str, slug_hint: str) -> tuple[str, int]:
    """把正文中的 http(s) 图片转存到 OSS，返回 (新 HTML, 成功张数)。

    单张失败不阻塞导入（保留原链接）。
    """
    if not _oss_ready(db):
        return html, 0

    config = oss_service.get_oss_config(db)
    client = httpx.Client(headers={"User-Agent": _UA}, timeout=30, follow_redirects=True)
    transferred = 0

    def _replace(match: re.Match) -> str:
        nonlocal transferred
        src = match.group(1)
        if _SKIP_SRC_RE.match(src):
            return match.group(0)
        try:
            resp = client.get(src)
            if resp.status_code != 200:
                return match.group(0)
            data = resp.content
            if len(data) > oss_service.MAX_SIZE:
                return match.group(0)
            content_type = _guess_content_type(src, resp)
            ext = oss_service._EXT_BY_TYPE.get(content_type, ".png")
            safe = re.sub(r"[^0-9a-zA-Z]+", "-", slug_hint)[:20].strip("-") or "img"
            key = f"blog/{datetime.utcnow():%Y%m}/import-{safe}-{secrets.token_hex(4)}{ext}"
            bucket, _ = oss_service._bucket(db)
            bucket.put_object(key, data, headers={"Content-Type": content_type})
            transferred += 1
            return match.group(0).replace(src, oss_service.public_url(config, key))
        except Exception:
            return match.group(0)  # 保留原图链接

    try:
        html = _IMG_RE.sub(_replace, html)
    finally:
        client.close()
    return html, transferred


def import_from_yuque(db: Session, url: str):
    """抓取公开语雀文档，生成一篇可编辑的草稿文章并返回。"""
    namespace, slug = parse_yuque_url(url)
    markdown = fetch_markdown(namespace, slug)
    if not markdown.strip():
        raise BizError("导入失败：文档内容为空")

    title, body_markdown = _split_title(markdown)
    if not title:
        title = fetch_page_title(namespace, slug)
    if not title:
        title = f"语雀导入 {datetime.utcnow():%Y-%m-%d}"

    body_html = _markdown.render(body_markdown)
    # 语雀图片转存到 OSS（已配置时），失败的单张保留原链接
    body_html, _transferred = transfer_images_to_oss(db, body_html, slug)
    return create_article(
        db,
        {
            "title": title[:255],
            "slug": slug,
            "body_html": body_html,
            "status": 0,  # 导入为草稿，编辑确认后再发布
        },
    )

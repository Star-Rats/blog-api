"""Redis 缓存：JSON 存取 + 前缀失效，读接口 cache-aside 用。

设计：
- REDIS_URL 未配置或 Redis 不可用时自动降级：所有操作静默跳过，接口照常查库
  （不可用后进入 30 秒冷却期，避免每个请求都等连接超时）
- 键统一以 "cache:" 前缀；管理端写操作完成后调用 bump() 全量失效
- 值一律 JSON 序列化，读取方自行反序列化/构造响应模型
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger("blog-api.cache")

PREFIX = "cache:"
DEFAULT_TTL = 600  # 秒；失效兜底，正常情况下写操作会主动 bump

_client: redis.Redis | None = None
_down_until = 0.0  # Redis 不可用时的冷却截止时间戳


def _get_client() -> redis.Redis | None:
    global _client
    url = get_settings().redis_url
    if not url:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def _mark(down: bool) -> None:
    """可用状态切换时记一条日志，避免刷屏。"""
    global _down_until
    if down:
        if _down_until <= time.time():
            _down_until = time.time() + 30
            logger.warning("Redis 不可用，缓存降级为直连数据库（30 秒后重试）")
    elif _down_until:
        _down_until = 0.0
        logger.info("Redis 已恢复")


def _down() -> bool:
    return time.time() < _down_until


def get(key: str) -> Any | None:
    """读缓存；未命中或 Redis 不可用返回 None。"""
    if _down():
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(PREFIX + key)
        _mark(False)
        return json.loads(raw) if raw is not None else None
    except Exception:
        _mark(True)
        return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    if _down():
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.set(PREFIX + key, json.dumps(value, ensure_ascii=False), ex=ttl)
        _mark(False)
    except Exception:
        _mark(True)


def bump() -> int:
    """使全部缓存失效（管理端写操作后调用）。返回清除的键数。"""
    if _down():
        return 0
    client = _get_client()
    if client is None:
        return 0
    try:
        keys = list(client.scan_iter(match=f"{PREFIX}*", count=200))
        if keys:
            client.delete(*keys)
        _mark(False)
        return len(keys)
    except Exception:
        _mark(True)
        return 0

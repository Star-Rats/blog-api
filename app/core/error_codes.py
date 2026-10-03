"""业务错误码统一封装（与前端 blog-admin/blog-index 的拦截器码表对齐）。

所有 /api 响应 HTTP 恒为 200，业务语义由 code 区分：
    2xxxx 成功
    4xxxx 客户端类错误（未登录/无权限/不存在）
    5xxxx 服务端类错误（系统异常/业务失败/参数错误）
"""
from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 20000
    NO_LOGIN = 40001
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    SYSTEM_ERROR = 50000
    FAIL = 51000
    VALID_ERROR = 52000  # 参数格式不正确

"""统一 ApiResponse 封装（对齐 Spring RestControllerAdvice 风格）。

所有 /api 响应统一为 {"code", "message", "data"}，HTTP 状态恒为 200，
业务语义由 code 区分（沿用原 Spring 项目的错误码段位）。
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ApiCode(IntEnum):
    SUCCESS = 20000
    NO_LOGIN = 40001
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    SYSTEM_ERROR = 50000
    FAIL = 51000
    VALID_ERROR = 52000  # 参数格式不正确


SUCCESS_MESSAGE = "操作成功"

# 统一封装的特征键：中间件据此识别"已是 ApiResponse"的响应（异常 advice 产出），避免二次包装
ENVELOPE_KEYS = {"code", "message", "data"}


class ApiResponse(BaseModel):
    code: int
    message: str
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None, message: str = SUCCESS_MESSAGE) -> "ApiResponse":
        return cls(code=ApiCode.SUCCESS, message=message, data=data)

    @classmethod
    def fail(cls, code: int, message: str) -> "ApiResponse":
        return cls(code=code, message=message, data=None)


def ok_json(data: Any = None, message: str = SUCCESS_MESSAGE) -> JSONResponse:
    """成功响应（HTTP 200 + code 20000）。"""
    return JSONResponse(ApiResponse.ok(data, message).model_dump())


def fail_json(code: int, message: str) -> JSONResponse:
    """失败响应（HTTP 200 + 业务错误码）。"""
    return JSONResponse(ApiResponse.fail(code, message).model_dump())

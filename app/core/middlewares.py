"""统一中间件：管理端鉴权 + HTTP 请求/响应日志（loguru）。

注册顺序（后注册在外层）：CORS → HttpLogMiddleware → AuthMiddleware → ApiEnvelopeMiddleware → 路由
- 日志在外层：能看到鉴权 401 与封装后的最终响应
- 鉴权在内层：401 响应直接返回统一封装，不再经过 EnvelopeMiddleware
"""
from __future__ import annotations

import json
import time
from typing import Any

import jwt
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.api_response import fail_json
from app.core.config import get_settings
from app.core.error_codes import ErrorCode


class AuthMiddleware(BaseHTTPMiddleware):
    """管理端统一鉴权：/api/admin/**（除登录）需要有效 Bearer JWT。

    通过后把管理员用户名写入 request.state.admin_username，供下游使用。
    """

    PROTECTED_PREFIX = "/api/admin"
    PUBLIC_PATHS = {"/api/admin/login"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(self.PROTECTED_PREFIX) or path in self.PUBLIC_PATHS:
            return await call_next(request)

        settings = get_settings()
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        payload: dict | None = None
        if token:
            try:
                payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return fail_json(ErrorCode.NO_LOGIN, "登录已过期，请重新登录")
            except jwt.PyJWTError:
                payload = None
        if not payload or payload.get("sub") != settings.admin_username:
            return fail_json(ErrorCode.NO_LOGIN, "未登录或登录已过期")
        request.state.admin_username = payload["sub"]
        return await call_next(request)


class HttpLogMiddleware(BaseHTTPMiddleware):
    """HTTP 访问日志：每个请求一条，同时包含请求与响应信息（loguru）。

    - 仅记录 /api/**；跳过 Swagger/OpenAPI
    - 请求体 JSON 脱敏（password/token 等）并截断；multipart 不记录内容
    - 响应记录 HTTP 状态、业务码与截断后的响应体；业务失败（code != 20000）记 WARNING
    """

    EXCLUDED_PREFIXES = ("/docs", "/openapi.json", "/redoc")
    MAX_BODY_LOG = 500
    SENSITIVE_KEYS = {"password", "token", "access_key_secret", "authorization"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") or any(path.startswith(p) for p in self.EXCLUDED_PREFIXES):
            return await call_next(request)

        start = time.perf_counter()
        req_repr = await self._request_repr(request)
        try:
            response = await call_next(request)
        except Exception as exc:
            self._log(request, 500, None, req_repr, f"<未处理异常> {exc!r}", start, error=True)
            raise

        body = b"".join([chunk async for chunk in response.body_iterator])
        code: Any = response.status_code
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                code = payload.get("code", payload.get("errno", response.status_code))
                resp_repr = self._truncate(json.dumps(payload, ensure_ascii=False))
            else:
                resp_repr = self._truncate(repr(payload))
        except Exception:
            resp_repr = self._truncate(repr(body))

        self._log(
            request,
            response.status_code,
            code,
            req_repr,
            resp_repr,
            start,
            error=isinstance(code, int) and code != ErrorCode.SUCCESS,
        )
        return self._rebuild(response, body)

    # ---- 辅助 ----

    def _log(
        self,
        request: Request,
        status: int,
        code: Any,
        req_repr: str,
        resp_repr: str,
        start: float,
        error: bool = False,
    ) -> None:
        elapsed_ms = (time.perf_counter() - start) * 1000
        client_ip = request.headers.get("x-real-ip") or (
            request.client.host if request.client else "-"
        )
        message = (
            f"{request.method} {request.url.path} -> {status}"
            f" code={code} {elapsed_ms:.0f}ms ip={client_ip}"
            f" req={req_repr} resp={resp_repr}"
        )
        (logger.warning if error else logger.info)(message)

    async def _request_repr(self, request: Request) -> str:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            return "<multipart/form-data>"
        body = await request.body()
        if not body:
            return "-"
        try:
            parsed = json.loads(body)
            return self._truncate(json.dumps(self._mask(parsed), ensure_ascii=False))
        except Exception:
            return self._truncate(repr(body[: self.MAX_BODY_LOG]))

    def _mask(self, obj: Any) -> Any:
        """递归脱敏敏感字段。"""
        if isinstance(obj, dict):
            return {
                key: ("***" if key.lower() in self.SENSITIVE_KEYS else self._mask(value))
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [self._mask(item) for item in obj]
        return obj

    def _truncate(self, text: str) -> str:
        if len(text) <= self.MAX_BODY_LOG:
            return text
        return f"{text[: self.MAX_BODY_LOG]}…(截断, 共{len(text)}字符)"

    @staticmethod
    def _rebuild(response: Response, body: bytes) -> Response:  # type: ignore[name-defined]
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() != "content-length"
        }
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.headers.get("content-type"),
        )

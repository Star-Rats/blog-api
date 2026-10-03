"""应用入口：uv run uvicorn app.main:app --reload"""
import json
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import admin, home, public
from app.core.api_response import ENVELOPE_KEYS, ApiResponse, fail_json
from app.core.error_codes import ErrorCode
from app.core.config import get_settings
from app.core.errors import AuthError, BizError
from app.core.middlewares import AuthMiddleware, HttpLogMiddleware

logger = logging.getLogger("blog-api")

app = FastAPI(
    title="Blog API",
    description="自托管博客后端（FastAPI + SQLAlchemy + MySQL）。"
    "文章在管理后台富文本编辑器中创作发布，分类与标签由博客系统自身维护。"
    "所有 /api 响应为统一 ApiResponse{code, message, data}，HTTP 恒为 200，业务语义由 code 区分。",
    version="1.2.0",
)


class ApiEnvelopeMiddleware(BaseHTTPMiddleware):
    """ResponseBodyAdvice 的等价物：把路由返回的 JSON 自动包成 ApiResponse。

    跳过：非 /api 路径（Swagger/OpenAPI）、异常 advice 已封装的响应、
    wangEditor 上传约定（含 errno 键）的响应。
    """

    EXCLUDED_PREFIXES = ("/docs", "/openapi.json", "/redoc")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api"):
            return response
        if any(path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES):
            return response
        if "application/json" not in response.headers.get("content-type", ""):
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(body)
        except Exception:
            return self._rebuild(response, body)
        if isinstance(payload, dict) and (
            ENVELOPE_KEYS <= payload.keys() or "errno" in payload
        ):
            return self._rebuild(response, body)
        wrapped = ApiResponse.ok(payload).model_dump()
        return JSONResponse(wrapped)

    @staticmethod
    def _rebuild(response: Response, body: bytes) -> Response:
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


# 注意注册顺序：后注册的在外层，CORS 必须能处理最终响应（含封装后）
app.add_middleware(ApiEnvelopeMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(HttpLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(home.router)
app.include_router(public.router)
app.include_router(admin.router)


# ---------- 全局异常 advice：所有异常统一转 ApiResponse ----------


@app.exception_handler(BizError)
async def biz_error_handler(_request: Request, exc: BizError):
    return fail_json(exc.code, exc.message)


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError):
    return fail_json(ErrorCode.NO_LOGIN, exc.message)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    code_by_status = {
        401: ErrorCode.NO_LOGIN,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
    }
    code = code_by_status.get(exc.status_code, ErrorCode.FAIL)
    message = str(exc.detail) if exc.detail else "请求失败"
    return fail_json(code, message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = f"参数格式不正确: {loc}: {first.get('msg', '')}" if loc else "参数格式不正确"
    return fail_json(ErrorCode.VALID_ERROR, message)


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, exc: Exception):
    logger.exception("未处理异常")
    return fail_json(ErrorCode.SYSTEM_ERROR, "系统异常，请稍后重试")


@app.get("/api/health", response_model=ApiResponse[dict], tags=["system"])
def health():
    return ApiResponse.ok({"status": "ok", "env": get_settings().app_env})

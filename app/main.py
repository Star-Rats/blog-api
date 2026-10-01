"""应用入口：uv run uvicorn app.main:app --reload"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, home, public
from app.core.config import get_settings
from app.core.errors import AuthError, BizError

app = FastAPI(
    title="Blog API",
    description="博客后端（FastAPI + SQLAlchemy + MySQL）。文章在管理后台富文本编辑器中创作发布，分类与标签由博客系统自身维护。",
    version="1.1.0",
)

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


@app.exception_handler(BizError)
async def biz_error_handler(_request: Request, exc: BizError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError):
    return JSONResponse(status_code=401, content={"detail": exc.message})


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "env": get_settings().app_env}

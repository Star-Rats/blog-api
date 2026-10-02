# blog-api 生产镜像：uv 官方镜像（内置 Python 3.14），依赖层缓存优化
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# 先复制依赖清单并同步（利用构建缓存：代码变更不触发重装依赖）
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# 再复制应用代码
COPY app ./app
COPY scripts ./scripts

ENV APP_ENV=prod
EXPOSE 8000

# PORT/WORKERS 可在 docker-compose.yml 中通过环境变量覆盖
CMD ["/bin/sh", "-c", ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-2}"]

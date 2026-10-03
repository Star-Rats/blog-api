# AGENTS.md

面向 coding agent 的仓库工作指南。

## 项目概述

自托管博客系统后端。文章在管理后台富文本编辑器中创作、发布；分类与标签由博客自身维护；图片上传阿里云 OSS；支持按公开链接导入语雀文档。

- 技术栈：Python 3.14 / FastAPI / SQLAlchemy 2.0 / MySQL 8，依赖用 uv 管理
- 相关仓库（同级目录）：`../blog-index`（主站前端）、`../blog-admin`（管理后台前端）

## 常用命令

```bash
uv sync                                        # 安装依赖（自动安装 Python 3.14）
uv run uvicorn app.main:app --reload --no-access-log  # 本地启动（访问日志由 HttpLogMiddleware 统一记录）
uv run python scripts/init_db.py               # 建库建表（自动创建数据库）
./deploy/deploy.sh install|update|backup       # Docker 生产部署（见 deploy/README.md）
uv run python -m compileall -q app scripts     # 语法检查
```

无自动化测试。改动后用 curl 冒烟验证：`/api/health`、`/api/home`、`/api/articles`、`/api/articles/{slug}`（浏览量应 +1）、管理端登录与列表。

## 分层约定（重要，改代码前先读）

```
api/          路由层：参数校验 → 调用下层 → 组装响应。禁止出现 ORM 查询（select/joinedload/db.execute）
repositories/ 数据访问：所有查询封装于此。前台"已发布"过滤规则统一在 articles._published_stmt()
services/     业务逻辑：写操作与事务边界（commit 在 service 内完成）
schemas/      Pydantic 请求/响应模型；ORM → 响应转换在 schemas/converters.py
db/           engine/session（get_db 依赖）与模型
```

## 统一中间件（core/middlewares.py）

- **AuthMiddleware**：管理端统一鉴权，保护 `/api/admin/**`（除 `/api/admin/login`），校验 Bearer JWT 后写入 `request.state.admin_username`。admin 路由无需再挂 `get_current_admin` 依赖
- **HttpLogMiddleware**：访问日志（loguru），每请求一条，同时含请求体（脱敏+截断）与响应体（截断）；业务失败（code != 20000）记 WARNING，multipart 不记录内容
- 中间件注册顺序（main.py）：Envelope（内）→ Auth → HttpLog → CORS（外）；新中间件按需插入并注意顺序
- 日志跳过 /docs、/openapi.json；`--no-access-log` 关闭 uvicorn 自带 access log

- 新查询先加到对应 repository，路由只调用
- repository 只做数据存取；业务校验、跨操作事务放 services
- `home.py` 等路由模块之间不得互相 import（曾经因此产生坏味道）

## 领域规则（改动前先读）

- 时间字段命名规范：所有表统一 `gmt_create`（创建时间，default=utcnow）/ `gmt_modify`（更新时间，onupdate=utcnow）；API 响应字段名保持 `created_at`/`updated_at`（converters.py 映射）。历史库的迁移已内置在 scripts/init_db.py（幂等）

- slug：仅小写字母/数字/连字符；留空自动生成 8 位随机串，冲突自动加后缀（services/articles.py）
- description / cover 留空 = 自动派生（正文前 120 字 / 正文第一张图），`derive_fields` 统一处理
- 前台可见 = `status == 1`（草稿不可见）；`published_at` 首次发布写入，之后保留
- 文章删除是硬删除；标签删除会解除文章关联
- 图片上传走 OSS（services/oss.py），OSS 配置存数据库 settings 表（管理端可改，Secret 掩码返回）
- 语雀导入（services/yuque_import.py）仅支持公开文档，走 `/markdown` 导出端点，无需 Token

## 缓存约定（core/cache.py）

- Redis 可选：`REDIS_URL` 留空或不通时自动降级直连数据库（不可用后 30 秒冷却重试），接口不受影响
- 读接口 cache-aside：先 `cache.get(key)`，未命中查库后 `cache.set(key, data)`（值一律 model_dump 后的 dict，JSON 序列化）
- 管理端写操作（articles/taxonomy/settings 各 service 的写函数）commit 后调 `cache.bump()` 全量失效；TTL 600 秒仅作兜底
- 键统一 `cache:` 前缀；缓存的对象是**响应数据**，浏览量等自增计数不进缓存、直接落库

## 响应约定（重要）

- 所有 `/api` 路由**显式返回** `ApiResponse.ok(data)`，并用泛型标注响应模型：`@router.get(..., response_model=ApiResponse[SomeOut])`（core/api_response.py）
- 响应统一为 `{code, message, data}`，HTTP 恒为 200，业务语义由 code 区分（ApiCode：20000 成功、40001 未登录、40400 不存在、51000 失败、52000 参数错误）
- 异常即 advice：业务错误抛 `BizError`、认证抛 `AuthError`、路由内用 `HTTPException`，由 main.py 全局 handler 统一转 ApiResponse；不要在路由里 try/except 拼响应
- main.py 的 `ApiEnvelopeMiddleware` 只作兜底（漏包的响应自动包装），不要依赖它
- 特例：`/api/admin/images` 返回 wangEditor 约定的 `{errno, ...}` 格式（中间件按 errno 键豁免），上传错误直接返回 `{errno:1, message}`
- 前端在 axios 拦截器统一解包（blog-admin/blog-index 的 src/api.js），改响应结构需同步两端

## 代码风格

- 注释、docstring、提交信息、错误文案一律中文
- SQLAlchemy 2.0 写法（`Mapped`/`mapped_column`/`select()`），禁用 legacy `Query`
- 类型标注用 `X | None` 语法
- 业务错误抛 `BizError(message)`（core/errors.py），由 main.py 全局 handler 转响应
- 时间统一 UTC naive；序列化用 `app/core/time.py` 的 `to_iso`

## 环境与配置

- `APP_ENV=dev|prod` 加载 `.env.dev` / `.env.prod`；真实环境变量优先级高于配置文件
- 本地开发连 Docker MySQL（127.0.0.1:3306，root/root，见 `.env.dev`）
- `.env.prod`、`data/`（MySQL 数据）、`backups/` 不进仓库；`.env.dev` 无真实密钥可入库
- 生产为 Docker 三容器（nginx/api/mysql，见 docker-compose.yml）；构建期代理用 `DOCKER_BUILD_PROXY`

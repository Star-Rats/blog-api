# blog

一个自托管博客系统：**文章在管理后台的富文本编辑器（wangEditor，语雀风格的写作体验）中直接创作、存草稿、发布**，分类与标签由博客自身维护。

技术栈：Python 3.14 / uv / FastAPI / SQLAlchemy 2.1 / MySQL 8；前端 Vue 3 + Vite（主站自定义样式，后台 Element Plus + wangEditor）。

## 职责划分

| 内容 | 在哪里维护 | 说明 |
| --- | --- | --- |
| 文章正文 | **管理后台编辑器** | 富文本写作，产出 HTML 存库；草稿不出现在前台 |
| 分类 / 标签 | 管理后台 | 独立 CRUD；编辑器内可直接给文章指派 |
| 站点设置 / 关于页 | 管理后台 | 标题、描述、页脚、关于页 Markdown |
| 浏览量 | 自动 | 文章详情访问 +1 |

文章字段派生逻辑（后端自动完成）：

- `slug`：留空自动生成 8 位随机串（可自定义，仅小写字母/数字/连字符），冲突自动加后缀
- `description`：留空自动取正文前 120 字；发布时清空即重新派生
- `cover`：留空自动取正文第一张图片
- `word_count`：按正文去除标签后的字符数统计
- `published_at`：首次发布时写入，之后保留

## 快速开始（dev）

```bash
# 1. 本地 Docker MySQL（已运行可跳过）
docker run -d --name mysql-8.0 -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root mysql:8.0.30

# 2. 安装 uv（如已安装可跳过）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 安装后端依赖（Python 版本由 .python-version 锁定 3.14）
cd blog && uv sync

# 4. 建库建表
uv run python scripts/init_db.py

# 5. 启动后端（:8000，Swagger 文档 /docs）
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 6. 启动前端
cd ../font/blog-index && npm install && npm run dev   # 主站 :5173
cd ../font/blog-admin && npm install && npm run dev   # 后台 :5174
```

后台地址 http://127.0.0.1:5174 （账号密码是后端 `.env.dev` 的 `ADMIN_USERNAME / ADMIN_PASSWORD`，默认 admin / admin123）。写作流程：**新建文章 → 编辑器写作 → 文章设置里选分类/标签 → 发布**，主站立刻可见。

## 环境区分（dev / prod）

通过 `APP_ENV` 切换，加载 `.env.dev` / `.env.prod`；真实环境变量优先级高于配置文件。env 里只有基础设施配置（数据库、管理员账号、站点名默认值）。

```bash
# 生产（先复制 .env.prod.example 为 .env.prod 并修改）
APP_ENV=prod uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# 前端构建（API 地址用构建时环境变量指定）
VITE_API_BASE=https://api.example.com npm run build
```

生产部署（Docker 一键）：nginx 网关（托管前端 + 反代 API）+ api + mysql 三容器编排，配置与数据全部挂载宿主机：

```bash
./deploy/deploy.sh install     # 首次部署（详见 deploy/README.md）
./deploy/deploy.sh update      # 日常更新
./deploy/deploy.sh backup      # 备份数据库
```

生产部署注意：

- 必须修改 `ADMIN_PASSWORD`、`JWT_SECRET`（install 时自动随机生成，可在 .env 再改）、数据库密码。
- 前端产物在各自 `dist/`，由 nginx 容器托管，路径在 `.env` 的 `WEB_INDEX_DIST` / `WEB_ADMIN_DIST` 配置。
- 编辑器图片上传到阿里云 OSS：在后台「站点设置 → 图片存储」配置 Endpoint/Bucket/AccessKey 后生效（配置存数据库，改完即时生效）。建议为 AccessKey 仅授予该 Bucket 的读写权限；如绑定 CDN 可填自定义域名。
- 主站 `index.html` 已带 `<meta name="referrer" content="no-referrer">`，外链图片不受 Referer 防盗链影响。
- 构建期需要代理拉取依赖时：`export DOCKER_BUILD_PROXY=http://宿主机代理:端口`（详见 deploy/README.md）。

## API 一览

### 前台（公开）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/home` | 首页聚合：站点信息、统计、最近文章、分类、标签 |
| GET | `/api/articles` | 文章分页列表，支持 `page`/`page_size`/`category_id`/`tag_id`/`keyword` |
| GET | `/api/articles/{slug}` | 文章详情（含 body_html，浏览量 +1） |
| GET | `/api/articles/archives` | 归档数据（含分类/标签，前端多视角聚合） |
| GET | `/api/about` | 「关于」页 Markdown 内容 |
| GET | `/api/categories`、`/api/tags` | 分类/标签列表（含文章数） |
| GET | `/api/health` | 健康检查 |

### 管理端（Bearer JWT）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/admin/login` | 登录 |
| GET/POST | `/api/admin/articles` | 文章列表 / 新建（草稿或发布） |
| GET/PUT/DELETE | `/api/admin/articles/{id}` | 详情（含 body_html）/ 编辑 / 删除 |
| GET/POST/PUT/DELETE | `/api/admin/categories` | 分类维护（有关联文章时禁止删除） |
| GET/POST/PUT/DELETE | `/api/admin/tags` | 标签维护 |
| GET/PUT | `/api/admin/settings` | 站点设置（含「关于我」Markdown） |
| GET/PUT/POST | `/api/admin/oss/config`、`/api/admin/oss/test` | OSS 配置（Secret 掩码返回）与连接测试 |
| POST | `/api/admin/images` | 编辑器图片上传（multipart，返回 URL） |
| GET | `/api/health` | 健康检查 |

## 项目结构

```
blog/                          # 后端（uv 管理，pyproject.toml + uv.lock）
├── app/
│   ├── main.py                # 应用入口（CORS、异常处理）
│   ├── core/                  # 配置（dev/prod）、JWT、异常、时间工具
│   ├── db/                    # engine/session + models（articles/categories/tags/article_tags/settings）
│   ├── schemas/               # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── articles.py        # 文章 CRUD、slug/摘要/字数/封面派生
│   │   ├── taxonomy.py        # 分类/标签维护、文章指派
│   ├── oss.py             # 阿里云 OSS 图片上传
│   │   └── settings.py        # 站点设置与「关于」内容
│   └── api/                   # home / public / admin 路由
└── scripts/init_db.py         # 建库建表
font/
├── blog-index/                # 主站（Vue3：首页/文章/归档聚合/关于）
└── blog-admin/                # 后台（Vue3 + Element Plus + wangEditor）
```

## 已验证的端到端场景

后台登录 → 编辑器写作（标题/段落/标题块/行内代码/代码块）→ 文章设置（分类、新建标签）→ 发布 → 主站首页与详情即时可见（浏览量自增）→ 转草稿/删除生效；草稿不出现在前台；slug 自动生成与自定义、摘要/封面自动派生、非法 slug 校验；分类/标签 CRUD 与删除保护；关于页 Markdown 渲染；图片上传 OSS（密钥错误等场景返回友好错误提示）；「导入语雀文章」：贴公开文档链接 → 抓取 /markdown → 渲染为可编辑草稿（标题自动提取），已配置 OSS 时自动把语雀图片转存到 Bucket 并替换 URL（单张失败保留原链接不阻塞导入）。

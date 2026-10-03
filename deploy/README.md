# Docker 一键部署指南

四个容器：**nginx（网关：前端 + API 反代）** / **api（FastAPI）** / **redis（缓存）** / **MySQL 8**。配置与数据全部挂载在宿主机（Redis 为纯缓存不持久化）。

## 前置要求

- 服务器已安装 Docker 与 Compose 插件（`curl -fsSL https://get.docker.com | sh`）
- 三个仓库放在同级目录（脚本默认按此布局找前端产物）：

```
/opt/blog/
├── blog-api/       # 本仓库
├── blog-index/     # 主站前端（npm run build 产出 dist/）
└── blog-admin/      # 后台前端（npm run build 产出 dist/）
```

## 一键部署

```bash
cd /opt/blog/blog-api
./deploy/deploy.sh install
```

脚本会：交互询问 **MySQL root 密码（必填）** 与 **管理员密码**（两次输入确认，留空自动生成）→ 生成 `.env`（JWT 密钥自动生成）→ 生成 HTTPS 证书（缺失时自签名）→ 构建镜像 → 启动 nginx/api/redis/mysql → 建库建表 → 健康检查。完成后按提示访问：

- 主站：`http://服务器IP/`
- 管理后台：`http://服务器IP/admin/`
- 接口文档：`http://服务器IP/docs`

## 服务器布局不同？

全部通过 `.env` 调整（脚本生成后可改，改完 `./deploy/deploy.sh restart`）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | `80` | nginx 对外端口（HTTP） |
| `PORT_SSL` | `443` | nginx 对外端口（HTTPS） |
| `WEB_INDEX_DIST` | `../blog-index/dist` | 主站构建产物目录 |
| `WEB_ADMIN_DIST` | `../blog-admin/dist` | 后台构建产物目录 |
| `DATA_DIR` | `./data` | 数据挂载目录（MySQL 数据、日志、证书） |
| `CERT_DIR` | `./data/certs` | HTTPS 证书目录（fullchain.pem / privkey.pem） |
| `SSL_DOMAIN` | `localhost` | 自签名证书的 CN |
| `WORKERS` | `2` | uvicorn 进程数 |
| `SITE_TITLE` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `JWT_SECRET` | 随机/默认 | 均可在生成后修改 |

已有外部 MySQL？删掉 compose 中 `mysql` 服务、api 的 `DB_HOST` 指向即可。

## 需要代理的环境

构建时容器内要从 PyPI 拉依赖：

```bash
export DOCKER_BUILD_PROXY=http://宿主机代理IP:端口   # 容器内访问宿主机代理用 host.docker.internal
./deploy/deploy.sh install
```

镜像拉取（nginx/uv 基础镜像）走 Docker daemon，按 Docker 官方文档为 daemon 配置代理，或先 `docker pull` 好所需镜像。

## 代码更新

**后端有改动**（blog-api 仓库）：

```bash
cd /opt/blog/blog-api
./deploy/deploy.sh update
```

一条命令完成：`git pull` 拉最新代码 → 重建 API 镜像 → 滚动重启（只有代码变化的容器会重建，nginx/redis/mysql 不动）→ 增量建表 → 健康检查。

**前端有改动**（blog-index / blog-admin 仓库）：`dist/` 是直接挂载进 nginx 的，不走镜像，在各自仓库里更新并重新构建即可，**构建完立即生效，无需重启任何容器**：

```bash
cd /opt/blog/blog-index && git pull && npm install && npm run build
cd /opt/blog/blog-admin && git pull && npm install && npm run build
```

**只改了配置**（`.env` 或 `deploy/nginx/`）：

```bash
./deploy/deploy.sh restart
# 只改了 nginx 配置可先校验语法：docker compose exec nginx nginx -t
```

## 日常运维

```bash
./deploy/deploy.sh update     # 更新后端：git pull → 重建 → 增量建表 → 重启
./deploy/deploy.sh backup     # 备份数据库到 backups/*.sql.gz（建议 crontab 每日一次）
./deploy/deploy.sh logs api   # 看日志（api/mysql/nginx）
./deploy/deploy.sh status     # 容器状态
./deploy/deploy.sh stop       # 停止（start 恢复）
./deploy/deploy.sh down       # 移除容器（数据/配置保留）
```

日志分两路：

- **落盘到宿主机**（`DATA_DIR/logs/`）：api 的完整访问/应用日志（loguru 文件 sink，50MB × 3 个滚动，`logs/api/api.log`），nginx 错误日志（`logs/nginx/error.log`）
- **stdout（Docker json-file 滚动，总上限 200MB）**：nginx 访问日志与所有容器 stdout，用 `./deploy/deploy.sh logs [api|mysql|nginx]` 查看

重启 nginx 使配置生效：`./deploy/deploy.sh restart` 后 `docker compose restart nginx`。

恢复备份：

```bash
gunzip < backups/blog-xxx.sql.gz | docker compose exec -T mysql sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" blog'
```

## HTTPS

nginx 同时监听 80 和 443（同一份站点配置）。**证书目录 `CERT_DIR`（默认 `./data/certs`）缺少证书时，install 会自动生成自签名证书**（浏览器提示不受信任，接口/功能不受影响）。

使用正式证书：

1. 将证书放到 `CERT_DIR` 下，命名为 `fullchain.pem` / `privkey.pem`（Let's Encrypt 的 `fullchain.pem`/`privkey.pem` 直接对应）
2. `./deploy/deploy.sh restart`，然后 `docker compose exec nginx nginx -t` 可校验

需要在 `.env` 调整：`PORT_SSL`（443 端口映射）、`SSL_DOMAIN`（自签名证书的 CN）、`CERT_DIR`。

## 安全清单

- [ ] `.env` 中的 `ADMIN_PASSWORD`、`JWT_SECRET`、`DB_ROOT_PASSWORD` 均非默认值（install 随机生成，可自行再改）
- [ ] 修改后 `./deploy/deploy.sh restart` 生效
- [ ] `.env` 与 `data/` 已在 `.gitignore` 中，不会进仓库

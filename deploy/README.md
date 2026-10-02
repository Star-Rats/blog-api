# Docker 一键部署指南

三个容器：**nginx（网关：前端 + API 反代）** / **api（FastAPI）** / **MySQL 8**。配置与数据全部挂载在宿主机。

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

脚本会：生成 `.env`（自动生成随机 JWT 密钥与管理员密码）→ 构建镜像 → 启动 nginx/api/mysql → 建库建表 → 健康检查。完成后按提示访问：

- 主站：`http://服务器IP/`
- 管理后台：`http://服务器IP/admin/`
- 接口文档：`http://服务器IP/docs`

## 服务器布局不同？

全部通过 `.env` 调整（脚本生成后可改，改完 `./deploy/deploy.sh restart`）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | `80` | nginx 对外端口 |
| `WEB_INDEX_DIST` | `../blog-index/dist` | 主站构建产物目录 |
| `WEB_ADMIN_DIST` | `../blog-admin/dist` | 后台构建产物目录 |
| `DATA_DIR` | `./data` | MySQL 数据挂载目录 |
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

## 日常运维

```bash
./deploy/deploy.sh update     # 更新：git pull → 重建 → 增量建表 → 重启
./deploy/deploy.sh backup     # 备份数据库到 backups/*.sql.gz（建议 crontab 每日一次）
./deploy/deploy.sh logs api   # 看日志（api/mysql/nginx）
./deploy/deploy.sh status     # 容器状态
./deploy/deploy.sh stop       # 停止（start 恢复）
./deploy/deploy.sh down       # 移除容器（数据/配置保留）
```

恢复备份：

```bash
gunzip < backups/blog-xxx.sql.gz | docker compose exec -T mysql sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" blog'
```

## HTTPS

最简单的方式是在宿主机另跑一层证书网关（certbot/caddy 监听 443，反代到 `127.0.0.1:$PORT`）；或自行把证书目录挂载进 nginx 容器并在 `deploy/nginx/conf.d/blog.conf` 增加 443 server 块。

## 安全清单

- [ ] `.env` 中的 `ADMIN_PASSWORD`、`JWT_SECRET`、`DB_ROOT_PASSWORD` 均非默认值（install 随机生成，可自行再改）
- [ ] 修改后 `./deploy/deploy.sh restart` 生效
- [ ] `.env` 与 `data/` 已在 `.gitignore` 中，不会进仓库

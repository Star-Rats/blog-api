#!/usr/bin/env bash
#
# blog-api Docker 一键部署（nginx 网关 + API + MySQL）
#
# 用法:
#   ./deploy/deploy.sh install     首次部署：生成 .env → 构建镜像 → 启动 nginx/api/mysql → 建库建表 → 健康检查
#   ./deploy/deploy.sh update      更新：git pull → 重建镜像 → 增量建表 → 平滑重启
#   ./deploy/deploy.sh start|stop|restart|status
#   ./deploy/deploy.sh logs [api|mysql|nginx]
#   ./deploy/deploy.sh backup      备份数据库到 backups/
#   ./deploy/deploy.sh down        停止并移除容器（数据保留在 ./data，配置保留在 .env）
#
# 非交互安装（CI/无人值守）通过环境变量传参:
#   PORT=80 SITE_TITLE=... ADMIN_USERNAME=... ADMIN_PASSWORD=...
#   WEB_INDEX_DIST=../blog-index/dist WEB_ADMIN_DIST=../blog-admin/dist DATA_DIR=./data
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

DC="docker compose"

info() { echo -e "\033[32m✓\033[0m $*"; }
warn() { echo -e "\033[33m!\033[0m $*"; }
fail() { echo -e "\033[31m✗\033[0m $*" >&2; exit 1; }

gen_secret() { openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

load_env() {
  # 读取 .env 供脚本使用（compose 会自动读取同一份文件）
  [ -f "$APP_DIR/.env" ] && { set -a; . "$APP_DIR/.env"; set +a; }
  PORT="${PORT:-80}"
  # 构建期代理：shell 里 export 了 https_proxy 时自动透传给 docker build（拉取 PyPI 依赖用）
  DOCKER_BUILD_PROXY="${DOCKER_BUILD_PROXY:-${https_proxy:-}}"
}

build_images() {
  info "构建 API 镜像..."
  DOCKER_BUILD_PROXY="$DOCKER_BUILD_PROXY" $DC build
  info "启动 nginx / api / mysql..."
  DOCKER_BUILD_PROXY="$DOCKER_BUILD_PROXY" $DC up -d
}

need_docker() {
  command -v docker >/dev/null 2>&1 || fail "未安装 Docker（yum install docker / apt install docker.io，或官方脚本 curl -fsSL https://get.docker.com | sh）"
  docker compose version >/dev/null 2>&1 || fail "缺少 Compose 插件（docker compose version 无法执行）"
}

# ---------- 子命令 ----------

cmd_install() {
  need_docker

  # 生成 .env（compose 与脚本共用）
  if [ -f "$APP_DIR/.env" ]; then
    info ".env 已存在，跳过生成"
  else
    info "生成 .env"
    local port="${PORT:-}" title="${SITE_TITLE:-}" admin_user="${ADMIN_USERNAME:-}" admin_password="${ADMIN_PASSWORD:-}"
    if [ -t 0 ]; then
      [ -z "$port" ] && read -r -p "对外端口 [80]: " port
      [ -z "$title" ] && read -r -p "站点标题 [My Blog]: " title
      [ -z "$admin_user" ] && read -r -p "管理员用户名 [admin]: " admin_user
    fi
    port="${port:-80}"; title="${title:-My Blog}"; admin_user="${admin_user:-admin}"
    if [ -z "$admin_password" ]; then
      admin_password="$(gen_secret)"
      info "已生成随机管理员密码: $admin_password"
    fi
    cat > "$APP_DIR/.env" <<EOF
# nginx 网关对外端口
PORT=$port
WORKERS=${WORKERS:-2}

# 数据库（root 密码；数据挂载在 ./data/mysql）
DB_ROOT_PASSWORD=$(gen_secret)
DB_NAME=blog

# 管理后台
ADMIN_USERNAME=$admin_user
ADMIN_PASSWORD=$admin_password
JWT_SECRET=$(gen_secret)

# 站点
SITE_TITLE="$title"

# 前端构建产物目录（相对本仓库；按你的部署布局调整）
WEB_INDEX_DIST="${WEB_INDEX_DIST:-../blog-index/dist}"
WEB_ADMIN_DIST="${WEB_ADMIN_DIST:-../blog-admin/dist}"

# 容器数据挂载目录（MySQL 数据）
DATA_DIR="${DATA_DIR:-./data}"
EOF
    chmod 600 "$APP_DIR/.env"
    warn "前端 dist 不存在时 nginx 会返回 404，请确认已构建两个前端仓库（npm run build）且目录与 .env 中路径一致"
  fi
  load_env

  build_images

  info "等待 MySQL 就绪并建库建表..."
  local ok=0
  for _ in $(seq 1 30); do
    if $DC exec -T api .venv/bin/python scripts/init_db.py >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  [ "$ok" = "1" ] || $DC exec -T api .venv/bin/python scripts/init_db.py   # 最后一次执行，把错误打出来
  info "数据库就绪"

  info "健康检查（经 nginx 网关）..."
  for _ in $(seq 1 15); do
    curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 || fail "健康检查未通过：docker compose logs api / nginx 排查"

  echo
  echo "==================== 部署完成 ===================="
  echo "  网关地址:    http://服务器IP:$PORT"
  echo "  博客主站:    $PORT 位置的 /"
  echo "  管理后台:    $PORT 位置的 /admin/ （账号见 .env 的 ADMIN_USERNAME/ADMIN_PASSWORD）"
  echo "  接口文档:    $PORT 位置的 /docs"
  echo "  数据位置:    $(cd "$APP_DIR" && cat .env | grep '^DATA_DIR=' | cut -d= -f2)/mysql （请定期 ./deploy/deploy.sh backup）"
  echo "  后续更新:    ./deploy/deploy.sh update"
  echo "==================================================="
}

cmd_update() {
  need_docker
  load_env
  cd "$APP_DIR"
  git pull --ff-only || warn "git pull 未生效（有本地改动？），使用当前代码继续"
  build_images
  $DC exec -T api .venv/bin/python scripts/init_db.py
  docker image prune -f >/dev/null 2>&1 || true
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null && info "更新完成，服务健康"
}

cmd_start()   { need_docker; $DC up -d; info "已启动"; }
cmd_stop()    { need_docker; $DC stop; info "已停止（./start 可再次启动）"; }
cmd_restart() { need_docker; $DC restart; info "已重启"; }
cmd_status()  { need_docker; $DC ps; }
cmd_logs()    { need_docker; $DC logs -f --tail=200 "${2:-}"; }

cmd_backup() {
  need_docker
  load_env
  mkdir -p "$APP_DIR/backups"
  local file="$APP_DIR/backups/blog-$(date +%Y%m%d-%H%M%S).sql.gz"
  $DC exec -T mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$DB_NAME"' | gzip > "$file"
  [ -s "$file" ] || fail "备份失败，请检查 MySQL 容器状态"
  info "已备份: $file ($(du -h "$file" | cut -f1))"
}

cmd_down() {
  need_docker
  $DC down
  warn "容器已移除；MySQL 数据保留在宿主机 DATA_DIR，配置保留在 .env"
}

case "${1:-install}" in
  install) cmd_install ;;
  update)  cmd_update ;;
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) need_docker; $DC restart; info "已重启" ;;
  status)  need_docker; $DC ps ;;
  logs)    need_docker; cmd_logs "$@" ;;
  backup)  cmd_backup ;;
  down)    cmd_down ;;
  uninstall) cmd_down ;;
  *)
    grep '^#   ' "$0" | sed 's/^#   //'
    exit 1
    ;;
esac

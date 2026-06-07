#!/bin/bash
# ==============================================================================
# 远程更新部署脚本 —— 从 GitHub 拉取最新代码并重启 Docker 服务
# ==============================================================================
# 用途：在服务器上一键拉取 GitHub 最新代码，重新构建并重启 Docker 容器
# 使用方式：
#   1. SSH 登录服务器
#   2. cd /data/study-monitor（项目目录）
#   3. bash scripts/remote-update.sh
#
# 前置条件：
#   - 服务器已安装 git + docker + docker-compose
#   - 服务器已 clone 项目仓库并配置好 remote
#   - docker-compose.yml 和 .env 已就绪
#
# 本地触发方式（从开发机执行）：
#   ssh root@115.223.38.172 -p 1000 "cd /data/study-monitor && bash scripts/remote-update.sh"
# ==============================================================================

set -e

# 项目目录（默认当前目录，可通过环境变量覆盖）
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJECT_DIR"

echo "=== 22中在线学习平台 - 远程更新部署 ==="
echo "项目目录: $PROJECT_DIR"
echo ""

# ── 步骤1: 拉取最新代码 ──
echo "[1/5] 拉取最新代码..."
git fetch origin
LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
  echo "  代码已是最新，无需更新 (commit: ${LOCAL_HASH:0:8})"
  SKIP_BUILD=true
else
  echo "  发现新代码:"
  git log --oneline HEAD..origin/main | head -5
  git pull origin main
  SKIP_BUILD=false
fi

# ── 步骤2: 检查依赖变更 ──
echo ""
echo "[2/5] 检查依赖变更..."
NEED_REBUILD=false

if [ "$SKIP_BUILD" = false ]; then
  # 检查关键文件是否有变更
  if git diff "$LOCAL_HASH" "$REMOTE_HASH" --name-only | grep -qE "requirements\.txt|Dockerfile|package\.json"; then
    NEED_REBUILD=true
    echo "  检测到依赖/Dockerfile 变更，需要重新构建镜像"
  else
    echo "  无依赖变更，但代码已更新，仍需重建"
    NEED_REBUILD=true
  fi
else
  echo "  代码未变更，跳过构建检查"
fi

# ── 步骤3: 构建镜像 ──
echo ""
if [ "$NEED_REBUILD" = true ]; then
  echo "[3/5] 重新构建 Docker 镜像..."
  docker compose build --no-cache
else
  echo "[3/5] 无需重新构建，跳过"
fi

# ── 步骤4: 重启服务 ──
echo ""
if [ "$NEED_REBUILD" = true ] || [ "$SKIP_BUILD" = false ]; then
  echo "[4/5] 重启 Docker 服务..."
  docker compose up -d --remove-orphans
else
  echo "[4/5] 无变更，跳过重启"
fi

# ── 步骤5: 健康检查 ──
echo ""
echo "[5/5] 健康检查..."
sleep 5

# 检查所有容器状态
if docker compose ps | grep -q "unhealthy\|Exit"; then
  echo "  ⚠ 有容器状态异常，请检查："
  docker compose ps
  echo ""
  echo "  查看日志: docker compose logs --tail=50"
  exit 1
else
  echo "  所有容器运行正常"
  docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
fi

echo ""
echo "========================================="
echo "  更新部署完成!"
VERSION=$(git describe --tags --always 2>/dev/null || echo "unknown")
echo "  版本: $VERSION"
COMMIT=$(git log -1 --oneline)
echo "  提交: $COMMIT"
echo ""
echo "  前端：http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'server-ip')"
echo "  API文档：http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'server-ip')/api/docs"
echo "========================================="

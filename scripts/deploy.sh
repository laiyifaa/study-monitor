#!/bin/bash
# 一键部署脚本

set -e

echo "=== 22中学习进度监督系统 - 部署脚本 ==="

# 检查 .env
if [ ! -f .env ]; then
  echo "创建 .env 文件..."
  cp backend/.env.example .env
  echo "请编辑 .env 文件，填入钉钉相关配置后重新运行"
  exit 1
fi

# 加载环境变量
source .env

echo "[1/4] 构建镜像..."
docker-compose build

echo "[2/4] 启动服务..."
docker-compose up -d

echo "[3/4] 等待数据库就绪..."
sleep 10

echo "[4/4] 检查服务状态..."
docker-compose ps

echo ""
echo "========================================="
echo "  部署完成!"
echo "  前端：http://your-server-ip"
echo "  API文档：http://your-server-ip/api/docs"
echo "========================================="

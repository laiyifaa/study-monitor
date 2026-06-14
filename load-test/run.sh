#!/bin/bash
# ============================================================
# 暑期在线学习平台 — 压测启动脚本
# ============================================================
#
# 使用方式：
#   ./run.sh                  # Web UI 模式（默认）
#   ./run.sh 200              # 无头模式，200 并发
#   ./run.sh 200 20 5m        # 无头模式，200用户，20/秒，5分钟
#   ./run.sh master           # 分布式 Master 模式
#   ./run.sh worker <IP>      # 分布式 Worker 模式
#
# 前置条件：
#   1. pip install -r requirements.txt
#   2. 确认目标服务器可达：curl http://115.223.38.172:1001/api/health
#   3. 如需视频流压测，先运行 fetch-video-names.sh 获取真实文件名
#
# ============================================================

set -e

HOST="http://115.223.38.172:1001"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCUST_FILE="$SCRIPT_DIR/locustfile.py"

# 检查 locust 是否安装
if ! command -v locust &> /dev/null; then
    echo "错误：locust 未安装，请先运行："
    echo "  pip install -r $SCRIPT_DIR/requirements.txt"
    exit 1
fi

# 检查目标服务器是否可达
echo "检查服务器连通性..."
if ! curl -s -o /dev/null -w "%{http_code}" "$HOST/api/health" | grep -q "200"; then
    echo "警告：服务器 $HOST 不可达，请检查网络连接"
    echo "继续执行压测可能会全部失败"
    read -p "是否继续？(y/N) " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        exit 1
    fi
fi

MODE="${1:-web}"

case "$MODE" in
    web)
        echo "=========================================="
        echo "  启动 Locust Web UI 模式"
        echo "  目标: $HOST"
        echo "  浏览器打开: http://localhost:8089"
        echo "=========================================="
        locust -f "$LOCUST_FILE" --host="$HOST"
        ;;

    master)
        WORKERS="${2:-3}"
        echo "=========================================="
        echo "  启动 Locust Master 模式"
        echo "  目标: $HOST"
        echo "  期望 Worker 数: $WORKERS"
        echo "  浏览器打开: http://localhost:8089"
        echo "=========================================="
        locust -f "$LOCUST_FILE" --host="$HOST" \
            --master --expect-workers="$WORKERS"
        ;;

    worker)
        MASTER_HOST="${2:-localhost}"
        echo "=========================================="
        echo "  启动 Locust Worker 模式"
        echo "  连接 Master: $MASTER_HOST:5557"
        echo "=========================================="
        locust -f "$LOCUST_FILE" --worker --master-host="$MASTER_HOST"
        ;;

    *[0-9]*)
        # 数字参数 → 无头模式
        USERS="${1:-200}"
        SPAWN_RATE="${2:-$((USERS / 10))}"
        RUN_TIME="${3:-3m}"
        CSV_PREFIX="$SCRIPT_DIR/results/loadtest_${USERS}u_$(date +%Y%m%d_%H%M%S)"

        # 确保 results 目录存在
        mkdir -p "$SCRIPT_DIR/results"

        echo "=========================================="
        echo "  启动 Locust 无头模式"
        echo "  目标:     $HOST"
        echo "  并发用户: $USERS"
        echo "  启动速率: $SPAWN_RATE/秒"
        echo "  运行时长: $RUN_TIME"
        echo "  CSV 报告: ${CSV_PREFIX}_*.csv"
        echo "=========================================="
        locust -f "$LOCUST_FILE" --host="$HOST" \
            --headless \
            -u "$USERS" \
            -r "$SPAWN_RATE" \
            -t "$RUN_TIME" \
            --csv="$CSV_PREFIX" \
            --html="${CSV_PREFIX}.html"
        echo ""
        echo "压测完成！报告文件："
        echo "  CSV: ${CSV_PREFIX}_stats.csv"
        echo "  HTML: ${CSV_PREFIX}.html"
        ;;

    *)
        echo "用法: $0 [web|master|worker|N [spawn_rate [run_time]]]"
        echo ""
        echo "  web              Web UI 模式（默认）"
        echo "  master           分布式 Master"
        echo "  worker <IP>      分布式 Worker"
        echo "  200              无头模式 200 并发"
        echo "  400 40 5m        无头模式 400 用户，40/秒，5分钟"
        exit 1
        ;;
esac

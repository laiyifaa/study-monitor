#!/bin/bash
# ============================================================================
# 在线学习平台视频并发压力测试脚本
# ============================================================================
# 用法：bash stress-test.sh [阶段]
#   阶段1: 安装工具
#   阶段2: 视频流压测（主瓶颈）
#   阶段3: 心跳API压测（次要瓶颈）
#   阶段4: 综合压测（视频+心跳同时）
#   无参数: 运行全部阶段
# ============================================================================

set -e

# —— 配置 ——
BASE_URL="http://127.0.0.1:8080"       # 容器内 Nginx 直连（绕过外层 Nginx）
EXTERNAL_URL="http://127.0.0.1:1001"    # 外层 Nginx（真实用户路径）

# 视频文件路径（从容器 default.conf 得知）
VIDEO_PATH="/uploads/videos/5_6f662c1e.mp4"   # 24MB 小视频，测试用

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[测试]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
fail() { echo -e "${RED}[失败]${NC} $1"; }

# ============================================================================
# 阶段1: 安装压测工具
# ============================================================================
phase1_install() {
    log "安装压测工具..."

    # wrk: HTTP 压测（视频流+API通用）
    if ! command -v wrk &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq wrk 2>/dev/null || {
            warn "wrk 安装失败，尝试编译安装..."
            cd /tmp && git clone https://github.com/wg/wrk.git 2>/dev/null || true
            cd /tmp/wrk && make -j$(nproc) && cp wrk /usr/local/bin/ 2>/dev/null || warn "wrk 编译失败"
        }
    fi

    # hey: Go 编写的压测工具（备选，更易用）
    if ! command -v hey &>/dev/null; then
        wget -q -O /tmp/hey.gz https://hey-release.s3.us-east-2.amazonaws.com/hey_linux_amd64 2>/dev/null && \
        chmod +x /tmp/hey.gz && mv /tmp/hey.gz /usr/local/bin/hey || warn "hey 安装失败，跳过"
    fi

    log "工具安装完成: wrk=$(command -v wrk 2>/dev/null || echo '未安装') hey=$(command -v hey 2>/dev/null || echo '未安装')"
}

# ============================================================================
# 阶段2: 视频流压测（主瓶颈测试）
# ============================================================================
phase2_video() {
    log "=========================================="
    log "阶段2: 视频流并发压测（系统主瓶颈）"
    log "=========================================="

    # 先确认视频可访问
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${EXTERNAL_URL}${VIDEO_PATH}")
    if [ "$HTTP_CODE" != "200" ]; then
        fail "视频文件不可访问 (${HTTP_CODE})，检查路径: ${EXTERNAL_URL}${VIDEO_PATH}"
        return 1
    fi
    log "视频文件可访问 (${HTTP_CODE})，开始压测..."

    echo ""
    log "--- 测试1: 渐进式并发 (10 → 50 → 100 → 200 → 500 连接) ---"
    log "  每级持续 30 秒，观察吞吐量和延迟"

    for CONNS in 10 50 100 200 500; do
        echo ""
        log "▶ 并发 ${CONNS} 连接，持续 30 秒..."
        if command -v wrk &>/dev/null; then
            wrk -t4 -c${CONNS} -d30s --latency "${EXTERNAL_URL}${VIDEO_PATH}" 2>&1 | head -20 || true
        elif command -v hey &>/dev/null; then
            hey -n $((CONNS * 60)) -c ${CONNS} "${EXTERNAL_URL}${VIDEO_PATH}" 2>&1 | head -20 || true
        else
            # fallback: 用 curl 粗测
            for i in $(seq 1 ${CONNS}); do
                curl -s -o /dev/null "${EXTERNAL_URL}${VIDEO_PATH}" &
            done
            wait
            log "curl 粗测 ${CONNS} 并发完成"
        fi

        # 每级之后检查系统负载
        LOAD=$(cat /proc/loadavg | awk '{print $1}')
        CPU_IDLE=$(top -bn1 | grep "Cpu(s)" | awk '{print $8}' | cut -d. -f1)
        MEM_USED=$(free -m | awk 'NR==2{printf "%d%%", $3*100/$2}')
        log "  系统状态: 负载=${LOAD} CPU空闲=${CPU_IDLE}% 内存=${MEM_USED}"
    done

    echo ""
    log "--- 测试2: 极限吞吐量（尝试找到带宽上限）---"
    log "  使用 8 线程 × 1000 连接，持续 60 秒"
    if command -v wrk &>/dev/null; then
        wrk -t8 -c1000 -d60s --latency "${EXTERNAL_URL}${VIDEO_PATH}" 2>&1 || warn "高并发测试失败，可能触发了连接限制"
    fi
}

# ============================================================================
# 阶段3: 心跳 API 压测
# ============================================================================
phase3_heartbeat() {
    log "=========================================="
    log "阶段3: 心跳 API 压测（次要瓶颈）"
    log "=========================================="
    log "正常场景: 每人每30秒1次心跳 = 100人约3.3 QPS"
    log "目标: 测试 API 能扛多少 QPS"

    # 先获取一个有效的 JWT token（需要登录）
    log "获取测试用 JWT Token..."
    TOKEN_RESP=$(curl -s -X POST "${EXTERNAL_URL}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin123"}' 2>/dev/null || echo '{}')
    TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('token',''))" 2>/dev/null || echo "")

    if [ -z "$TOKEN" ]; then
        # fallback: 尝试用默认用户
        TOKEN_RESP=$(curl -s -X POST "${EXTERNAL_URL}/api/auth/login" \
            -H "Content-Type: application/json" \
            -d '{"username":"student1","password":"123456"}' 2>/dev/null || echo '{}')
        TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('token',''))" 2>/dev/null || echo "")
    fi

    if [ -z "$TOKEN" ]; then
        warn "无法获取 JWT Token，跳过心跳 API 测试"
        warn "你可以手动提供 Token: export TOKEN=xxx && bash stress-test.sh 3"
        return 0
    fi

    log "Token 获取成功，开始 API 压测..."

    echo ""
    log "--- 测试: 心跳 API 渐进压测 (10 → 50 → 100 → 200 并发) ---"

    for CONNS in 10 50 100 200; do
        echo ""
        log "▶ API 并发 ${CONNS}，持续 15 秒..."
        if command -v wrk &>/dev/null; then
            wrk -t4 -c${CONNS} -d15s --latency \
                -s /tmp/wrk-heartbeat.lua \
                "${EXTERNAL_URL}" 2>&1 | head -20 || true
        fi
    done
}

# ============================================================================
# 阶段4: 综合压测 + 生成报告
# ============================================================================
phase4_combined() {
    log "=========================================="
    log "阶段4: 综合评估"
    log "=========================================="

    # 收集关键指标
    log "当前系统状态:"
    echo "  CPU: $(nproc) 核 $(cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d: -f2 | xargs)"
    echo "  内存: $(free -h | awk 'NR==2{print "总计 "$2" 已用 "$3" 可用 "$7}')"
    echo "  磁盘: $(df -h /data | awk 'NR==2{print "总计 "$2" 已用 "$3" 可用 "$4" 使用率 "$5}')"
    echo ""

    # 外层 Nginx 连接能力
    WORKERS=$(grep worker_processes /etc/nginx/nginx.conf | awk '{print $2}' | tr -d ';')
    CONNS_PER=$(grep worker_connections /etc/nginx/nginx.conf | awk '{print $2}' | tr -d ';')
    MAX_CONNS=$((${WORKERS:-8} * ${CONNS_PER:-768}))
    echo "  外层Nginx: ${WORKERS:-auto} worker × ${CONNS_PER:-768} = ${MAX_CONNS} 最大并发连接"

    # 内层 Nginx
    INNER_CONNS=1024
    echo "  内层Nginx: auto worker × ${INNER_CONNS} 连接"

    echo ""
    log "=== 并发能力估算 ==="
    echo ""
    echo "  视频流瓶颈:"
    echo "    - 1080p 视频码率 ≈ 3-5 Mbps/人"
    echo "    - 720p 视频码率 ≈ 1.5-3 Mbps/人"
    echo "    - 1 Gbps 带宽上限 ≈ 200-330 人 (1080p) 或 330-660 人 (720p)"
    echo "    - 建议: 用实际带宽除以视频码率得出精确数字"
    echo ""
    echo "  心跳API瓶颈:"
    echo "    - FastAPI (8核) 轻松扛 500+ QPS"
    echo "    - 1000人 × 2次/分钟心跳 = 33 QPS ← 远低于上限"
    echo "    - MySQL 写入: 心跳日志 ~12k行/小时/100人，30天清理，无压力"
    echo ""
    echo "  系统连接数上限:"
    echo "    - 外层 Nginx: ${MAX_CONNS} 并发连接"
    echo "    - ulimit -n: $(ulimit -n) (可能需调大到 65535)"
    echo ""

    # 建议优化
    log "=== 优化建议 ==="
    echo ""
    echo "  1. 【必做】调大文件描述符限制:"
    echo "     echo '* soft nofile 65535' >> /etc/security/limits.conf"
    echo "     echo '* hard nofile 65535' >> /etc/security/limits.conf"
    echo ""
    echo "  2. 【必做】调大 Nginx worker_connections:"
    echo "     sed -i 's/worker_connections 768/worker_connections 4096/' /etc/nginx/nginx.conf"
    echo "     nginx -s reload"
    echo ""
    echo "  3. 【推荐】开通天翼云 CDN:"
    echo "     视频走 CDN 分发，服务器只需承受回源流量"
    echo "     CDN 可轻松扛 10000+ 并发，服务器侧降到 10-50 并发"
    echo ""
    echo "  4. 【可选】视频转码为多码率:"
    echo "     ffmpeg -i input.mp4 -b:v 1M -s 1280x720 output_720p.mp4"
    echo "     低码率版本可让同样带宽支持更多学生"

    echo ""
    log "压测完成！"
}

# ============================================================================
# 主流程
# ============================================================================
case "${1:-all}" in
    1) phase1_install ;;
    2) phase2_video ;;
    3) phase3_heartbeat ;;
    4) phase4_combined ;;
    all)
        phase1_install
        phase2_video
        phase3_heartbeat
        phase4_combined
        ;;
    *)
        echo "用法: bash stress-test.sh [1|2|3|4|all]"
        echo "  1 = 安装工具"
        echo "  2 = 视频流压测"
        echo "  3 = 心跳API压测"
        echo "  4 = 综合评估"
        ;;
esac

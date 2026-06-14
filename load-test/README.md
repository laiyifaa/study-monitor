---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '40179efb-acf6-422c-ba98-cbaf58c57df0'
  PropagateID: '40179efb-acf6-422c-ba98-cbaf58c57df0'
  ReservedCode1: '64e3f38f-f6b1-4c9b-8e44-f698267a908a'
  ReservedCode2: '64e3f38f-f6b1-4c9b-8e44-f698267a908a'
---

# 暑期在线学习平台 — 压测方案

## 概述

对 `http://115.223.38.172:1001` 进行压力测试，确定系统在高并发下的表现和瓶颈。

### 服务器规格
- CPU: 8核 Xeon Gold 5218
- 内存: 15GB
- 磁盘: HDD 50GB+300GB
- 上行带宽: 597 Mbps / 下行: 4.9 Mbps
- 服务: Docker + Nginx (sendfile) + FastAPI + MySQL + Redis

### 压测三轮递进

| 轮次 | 并发数 | 目的 |
|------|--------|------|
| 第一轮 | 200 | 验证基础承载能力 |
| 第二轮 | 400 | 发现瓶颈点 |
| 第三轮 | 800 | 极限测试，确认 HDD + 带宽上限 |

## 脚本说明

| 文件 | 用途 |
|------|------|
| `locustfile.py` | 主压测脚本 — 模拟完整业务流程（学生70% + 视频20% + 教师10%） |
| `video_only.py` | 视频流专用 — 纯测试 Nginx sendfile 并发视频分发极限 |
| `run.sh` | 快速启动脚本 |
| `fetch-video-names.sh` | 从服务器同步真实视频文件名 |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. （可选）同步服务器视频文件名
./fetch-video-names.sh

# 3a. Web UI 模式 — 浏览器打开 http://localhost:8089
./run.sh web

# 3b. 无头模式 — 三轮递进
./run.sh 200 20 3m     # 第一轮
./run.sh 400 40 3m     # 第二轮
./run.sh 800 80 5m     # 第三轮
```

## 分布式压测

单机带宽不足以打满 597 Mbps 服务器上行，需多台云主机作为负载生成器。

```bash
# 主控机（天翼云 VM #1）
./run.sh master

# 从属机（天翼云 VM #2, #3, ...）
./run.sh worker <MASTER_IP>
```

> 关键：负载机总下行带宽必须 >> 597 Mbps。
> 建议至少 3 台天翼云 VM（每台 200Mbps），总计 600Mbps。

## 视频流极限测试

如需单独测试 Nginx 视频分发极限（与 API 无关）：

```bash
locust -f video_only.py --host=http://115.223.38.172:1001 \
    --headless -u 800 -r 50 -t 5m --csv=video_result
```

预期瓶颈：HDD 随机读 ~20MB/s，先于带宽 74.6MB/s 到达。

## 结果文件

无头模式运行后，`results/` 目录生成：
- `*_stats.csv` — 请求统计
- `*_stats_history.csv` — 时间序列数据
- `*_failures.csv` — 失败记录
- `*.html` — HTML 可视化报告

## 注意事项

1. **带宽陷阱**：负载机带宽 < 服务器上行带宽 → 压不到服务器极限
2. **数据库数据**：压测会创建大量 study_session 和 heartbeat_log，结束后可清理
3. **Redis 限流**：心跳接口有每分钟5次限制，Locust 并发可能触发 429（正常）
4. **视频404**：如视频文件名变更，需运行 `fetch-video-names.sh` 或手动更新
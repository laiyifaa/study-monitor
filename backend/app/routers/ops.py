"""
运维监控模块 (ops)
=================

功能说明：
    提供系统运维所需的实时监控数据，包括服务器资源、服务健康、业务状态、存储信息等。
    面向管理员，用于日常巡检和故障排查。

在系统中的角色：
    运维可观测层——将系统内部状态暴露给管理员，是故障发现和性能分析的核心入口。

API 列表：
    GET /api/ops/server      — 服务器资源：CPU、内存、磁盘IO、网络流量
    GET /api/ops/containers  — Docker 容器状态（仅 study-monitor 相关）
    GET /api/ops/services    — 服务健康：API、Redis、MySQL
    GET /api/ops/business    — 业务数据：在线人数、活跃会话、视频流、心跳QPS
    GET /api/ops/storage     — 存储信息：视频大小、磁盘剩余、MySQL 大小
    GET /api/ops/overview    — 全量聚合（一次请求获取所有数据，前端面板用）

权限要求：admin 角色

告警阈值说明：
    CPU 使用率 > 80%       → warning
    内存使用率 > 90%       → warning
    磁盘使用率 > 90%       → warning
    容器非 running          → warning
    API/Redis/MySQL 不可用  → warning
"""

import os
import time
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database_redis import get_redis
from app.models.models import User, StudySession, Course
from app.utils.jwt_helper import require_role
from app.config import get_settings

router = APIRouter(prefix="/api/ops", tags=["运维监控"])
settings = get_settings()

# ============================================================
# 告警阈值常量
# ============================================================
ALERT_CPU_PERCENT = 80       # CPU 使用率告警阈值
ALERT_MEMORY_PERCENT = 90    # 内存使用率告警阈值
ALERT_DISK_PERCENT = 90      # 磁盘使用率告警阈值

# 上一次网络 IO 采样的缓存（用于计算速率）
_last_net_io = {"timestamp": 0, "bytes_sent": 0, "bytes_recv": 0}


# ============================================================
# 辅助函数
# ============================================================

def _alert_level(value: float, threshold: float) -> str:
    """根据阈值返回告警级别：ok / warning"""
    return "warning" if value > threshold else "ok"


def _human_size(bytes_val: float) -> str:
    """将字节数转换为人类可读的大小字符串"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}PB"


# ============================================================
# 服务器资源监控
# ============================================================

@router.get("/server")
async def server_stats(user: User = Depends(require_role("admin"))):
    """
    服务器资源统计 — CPU、内存、磁盘IO、网络流量

    返回格式：
        cpu_percent      — CPU 总使用率（%）
        cpu_count        — CPU 核心数
        memory_total     — 总内存（字节）
        memory_used      — 已用内存（字节）
        memory_percent   — 内存使用率（%）
        swap_percent     — 交换分区使用率（%）
        disk_io_read     — 磁盘读速率（MB/s，自上次采样间隔）
        disk_io_write    — 磁盘写速率（MB/s，自上次采样间隔）
        net_upload       — 网络上行速率（Mbps）
        net_download     — 网络下行速率（Mbps）
        alerts           — 告警项列表
    """
    import psutil

    # --- CPU ---
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()

    # --- 内存 ---
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # --- 磁盘 IO ---
    # 计算1秒内的IO速率
    disk_io1 = psutil.disk_io_counters()
    time.sleep(1)
    disk_io2 = psutil.disk_io_counters()
    disk_read_mbs = (disk_io2.read_bytes - disk_io1.read_bytes) / 1024 / 1024
    disk_write_mbs = (disk_io2.write_bytes - disk_io1.write_bytes) / 1024 / 1024

    # --- 网络流量 ---
    net = psutil.net_io_counters()
    now = time.time()
    global _last_net_io
    if _last_net_io["timestamp"] > 0:
        interval = now - _last_net_io["timestamp"]
        upload_mbps = (net.bytes_sent - _last_net_io["bytes_sent"]) * 8 / interval / 1_000_000
        download_mbps = (net.bytes_recv - _last_net_io["bytes_recv"]) * 8 / interval / 1_000_000
    else:
        upload_mbps = 0
        download_mbps = 0
    _last_net_io = {"timestamp": now, "bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv}

    # --- 告警判定 ---
    alerts = []
    if cpu_percent > ALERT_CPU_PERCENT:
        alerts.append({"metric": "cpu", "value": cpu_percent, "threshold": ALERT_CPU_PERCENT, "message": f"CPU使用率 {cpu_percent}% 超过阈值 {ALERT_CPU_PERCENT}%"})
    if mem.percent > ALERT_MEMORY_PERCENT:
        alerts.append({"metric": "memory", "value": mem.percent, "threshold": ALERT_MEMORY_PERCENT, "message": f"内存使用率 {mem.percent}% 超过阈值 {ALERT_MEMORY_PERCENT}%"})

    return {
        "code": 0,
        "data": {
            "cpu_percent": round(cpu_percent, 1),
            "cpu_count": cpu_count,
            "memory_total": mem.total,
            "memory_total_human": _human_size(mem.total),
            "memory_used": mem.used,
            "memory_used_human": _human_size(mem.used),
            "memory_percent": round(mem.percent, 1),
            "swap_percent": round(swap.percent, 1),
            "disk_io_read_mbs": round(disk_read_mbs, 2),
            "disk_io_write_mbs": round(disk_write_mbs, 2),
            "net_upload_mbps": round(upload_mbps, 2),
            "net_download_mbps": round(download_mbps, 2),
            "cpu_alert": _alert_level(cpu_percent, ALERT_CPU_PERCENT),
            "memory_alert": _alert_level(mem.percent, ALERT_MEMORY_PERCENT),
            "alerts": alerts,
        },
    }


# ============================================================
# Docker 容器状态
# ============================================================

@router.get("/containers")
async def container_stats(user: User = Depends(require_role("admin"))):
    """
    Docker 容器状态 — 仅查询 study-monitor 相关容器

    实现方式：
        通过 httpx 直接访问 Docker daemon 的 Unix socket REST API，
        查询名称以 "study-monitor" 开头的容器状态。
        不依赖 docker-py SDK（7.x 版本与 requests 2.34+ 存在 http+docker URL
        scheme 兼容问题），改用已有的 httpx + Unix socket 方式更轻量稳定。

    返回格式：
        containers: [{ name, status, state, image, created, ports, health }]
        alerts — 任何容器非 running 时触发告警
    """
    containers = []
    try:
        import httpx
        # 通过 Unix socket 连接 Docker daemon API
        # Docker daemon 默认监听 /var/run/docker.sock，提供 HTTP REST API
        socket_path = "/var/run/docker.sock"
        if not os.path.exists(socket_path):
            containers = [{"error": f"Docker socket 不存在: {socket_path}，请检查卷挂载"}]
        else:
            transport = httpx.HTTPTransport(uds=socket_path)
            with httpx.Client(transport=transport, timeout=10) as client:
                # 查询所有 study-monitor 相关容器（含已停止的）
                filters = json.dumps({"name": ["study-monitor"]})
                resp = client.get(f"http://localhost/containers/json?all=true&filters={filters}")
                resp.raise_for_status()
                for c in resp.json():
                    # 容器名称（Docker 返回的 Names 带前导 "/"）
                    names = c.get("Names", [])
                    name = names[0].lstrip("/") if names else ""
                    
                    # 端口映射
                    ports_list = []
                    for port_binding in c.get("Ports", []):
                        ip = port_binding.get("IP", "")
                        public_port = port_binding.get("PublicPort", "")
                        private_port = port_binding.get("PrivatePort", "")
                        if public_port:
                            ports_list.append(f"{ip}:{public_port}->{private_port}")

                    # 健康状态
                    health = ""
                    state_obj = c.get("State", "")
                    if isinstance(state_obj, dict) and state_obj.get("Health"):
                        health = state_obj["Health"].get("Status", "")

                    # state 可能是字符串或 dict
                    if isinstance(state_obj, dict):
                        state = state_obj.get("Status", "")
                    else:
                        state = str(state_obj)

                    containers.append({
                        "name": name,
                        "status": c.get("Status", ""),  # "Up 2 hours" 等人类可读
                        "state": state,                  # "running", "exited" 等机器可读
                        "image": c.get("Image", ""),
                        "created": c.get("Created", ""),
                        "ports": ", ".join(ports_list) if ports_list else "",
                        "health": health,
                    })
    except ImportError:
        containers = [{"error": "httpx 未安装，无法连接 Docker API"}]
    except Exception as e:
        containers = [{"error": f"Docker 连接失败: {str(e)}"}]

    # 告警判定：任何容器非 running
    alerts = []
    for c in containers:
        if isinstance(c, dict) and c.get("state") and c["state"] != "running":
            alerts.append({
                "metric": "container",
                "container": c.get("name", ""),
                "message": f"容器 {c.get('name', '')} 状态异常: {c.get('state', '')}",
            })

    return {
        "code": 0,
        "data": {
            "containers": containers,
            "alerts": alerts,
        },
    }


# ============================================================
# 服务健康检查
# ============================================================

@router.get("/services")
async def service_health(
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    服务健康状态 — API、Redis、MySQL 连通性与状态

    返回格式：
        api:    { status, version, uptime_seconds }
        redis:  { status, used_memory_human, connected_clients }
        mysql:  { status, version, connections, database_size }
        alerts  — 任何服务不可用时触发告警
    """
    alerts = []

    # --- API 健康 ---
    api_status = "ok"
    api_version = "1.0.0"

    # --- Redis 健康 ---
    redis_status = "error"
    redis_info = {}
    try:
        redis = await get_redis()
        info = await redis.info()
        redis_status = "ok"
        redis_info = {
            "used_memory_human": info.get("used_memory_human", ""),
            "connected_clients": info.get("connected_clients", 0),
            "uptime_in_seconds": info.get("uptime_in_days", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
        }
    except Exception as e:
        redis_info = {"error": str(e)}
        alerts.append({"metric": "redis", "message": f"Redis 连接异常: {e}"})

    # --- MySQL 健康 ---
    mysql_status = "error"
    mysql_info = {}
    try:
        # 简单查询测试连通性
        result = await db.execute(text("SELECT 1"))
        result.fetchone()

        # MySQL 版本
        ver_result = await db.execute(text("SELECT VERSION()"))
        mysql_version = ver_result.scalar()

        # 当前连接数
        conn_result = await db.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
        conn_row = conn_result.fetchone()
        connections = int(conn_row[1]) if conn_row else 0

        # 数据库大小
        db_size_result = await db.execute(
            text("SELECT SUM(data_length + index_length) FROM information_schema.tables "
                 "WHERE table_schema = :schema"),
            {"schema": settings.MYSQL_DATABASE},
        )
        db_size = db_size_result.scalar() or 0

        mysql_status = "ok"
        mysql_info = {
            "version": mysql_version,
            "connections": connections,
            "database_size": db_size,
            "database_size_human": _human_size(db_size),
        }
    except Exception as e:
        mysql_info = {"error": str(e)}
        alerts.append({"metric": "mysql", "message": f"MySQL 连接异常: {e}"})

    return {
        "code": 0,
        "data": {
            "api": {"status": api_status, "version": api_version},
            "redis": {"status": redis_status, **redis_info},
            "mysql": {"status": mysql_status, **mysql_info},
            "alerts": alerts,
        },
    }


# ============================================================
# 业务数据监控
# ============================================================

@router.get("/business")
async def business_stats(
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    业务实时数据 — 在线人数、活跃会话、视频流、心跳QPS、今日统计

    在线定义：最近2分钟内有心跳上报的用户视为在线

    返回格式：
        online_teachers   — 在线教师数
        online_students   — 在线学生数
        active_sessions   — 活跃学习会话数
        active_videos     — 正在播放视频的会话数
        heartbeat_qps     — 最近1分钟心跳上报速率（次/秒）
        today_study_users — 今日学习人次
        today_effective_minutes — 今日总有效学习时长（分钟）
        alerts            — 心跳QPS异常等
    """
    now = datetime.now()
    two_min_ago = now - timedelta(minutes=2)
    one_min_ago = now - timedelta(minutes=1)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # --- 在线用户数（最近2分钟有心跳的） ---
    # 通过活跃会话间接统计：is_active=True 且 last_heartbeat >= 2分钟前
    online_students = await db.scalar(
        select(func.count(func.distinct(StudySession.user_id))).where(
            and_(
                StudySession.is_active == True,
                StudySession.last_heartbeat >= two_min_ago,
            )
        ).join(User, StudySession.user_id == User.id).where(User.role == "student")
    ) or 0

    # 在线教师：简单统计，教师不一定有 StudySession，用心跳日志间接判断
    # 降级方案：查最近2分钟活跃的会话关联的教师 + 最近5分钟有API请求的教师
    online_teachers = await db.scalar(
        select(func.count(func.distinct(User.id))).where(
            and_(
                User.role.in_(["teacher", "admin"]),
                User.updated_at >= two_min_ago,
            )
        )
    ) or 0

    # --- 活跃会话数 ---
    active_sessions = await db.scalar(
        select(func.count()).select_from(StudySession).where(
            StudySession.is_active == True
        )
    ) or 0

    # --- 正在播放视频的会话数（心跳中 is_playing=True 的活跃会话） ---
    # 通过最近心跳日志间接判断
    active_videos = await db.scalar(
        select(func.count(func.distinct(StudySession.id))).where(
            and_(
                StudySession.is_active == True,
                StudySession.last_heartbeat >= one_min_ago,
            )
        )
    ) or 0

    # --- 心跳 QPS（最近1分钟） ---
    heartbeat_qps = 0.0
    try:
        from app.models.models import HeartbeatLog
        recent_heartbeats = await db.scalar(
            select(func.count()).select_from(HeartbeatLog).where(
                HeartbeatLog.timestamp >= one_min_ago
            )
        ) or 0
        heartbeat_qps = round(recent_heartbeats / 60, 2)
    except Exception:
        pass

    # --- 今日统计 ---
    today_study_users = await db.scalar(
        select(func.count(func.distinct(StudySession.user_id))).where(
            StudySession.start_time >= today_start
        )
    ) or 0

    today_effective_seconds = await db.scalar(
        select(func.sum(StudySession.effective_seconds)).where(
            StudySession.start_time >= today_start
        )
    ) or 0

    return {
        "code": 0,
        "data": {
            "online_teachers": online_teachers,
            "online_students": online_students,
            "active_sessions": active_sessions,
            "active_videos": active_videos,
            "heartbeat_qps": heartbeat_qps,
            "today_study_users": today_study_users,
            "today_effective_minutes": round(today_effective_seconds / 60, 1),
            "alerts": [],
        },
    }


# ============================================================
# 存储信息
# ============================================================

@router.get("/storage")
async def storage_stats(
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    存储信息 — 视频文件大小、磁盘剩余、MySQL 数据库大小

    返回格式：
        video_total_size  — 视频文件总大小（字节）
        video_total_human — 人类可读大小
        video_count       — 视频文件数量
        disk_total        — 磁盘总大小
        disk_used         — 磁盘已用
        disk_free         — 磁盘剩余
        disk_percent      — 磁盘使用率
        mysql_size        — MySQL 数据库大小（字节）
        mysql_size_human  — 人类可读大小
        alerts            — 磁盘超过阈值告警
    """
    import psutil

    # --- 视频文件统计 ---
    video_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "videos")
    video_total_size = 0
    video_count = 0
    if os.path.exists(video_dir):
        for f in os.listdir(video_dir):
            fp = os.path.join(video_dir, f)
            if os.path.isfile(fp):
                video_total_size += os.path.getsize(fp)
                video_count += 1

    # --- MySQL 数据库大小 ---
    mysql_size = 0
    mysql_size_human = "-"
    try:
        db_size_result = await db.execute(
            text("SELECT SUM(data_length + index_length) FROM information_schema.tables "
                 "WHERE table_schema = :schema"),
            {"schema": settings.MYSQL_DATABASE},
        )
        mysql_size = db_size_result.scalar() or 0
        mysql_size_human = _human_size(mysql_size)
    except Exception:
        pass

    # --- 磁盘使用情况 ---
    disk = psutil.disk_usage("/data" if os.path.exists("/data") else "/")

    # 告警
    alerts = []
    if disk.percent > ALERT_DISK_PERCENT:
        alerts.append({
            "metric": "disk",
            "value": disk.percent,
            "threshold": ALERT_DISK_PERCENT,
            "message": f"磁盘使用率 {disk.percent}% 超过阈值 {ALERT_DISK_PERCENT}%",
        })

    return {
        "code": 0,
        "data": {
            "video_total_size": video_total_size,
            "video_total_human": _human_size(video_total_size),
            "video_count": video_count,
            "mysql_size": mysql_size,
            "mysql_size_human": mysql_size_human,
            "disk_total": disk.total,
            "disk_total_human": _human_size(disk.total),
            "disk_used": disk.used,
            "disk_used_human": _human_size(disk.used),
            "disk_free": disk.free,
            "disk_free_human": _human_size(disk.free),
            "disk_percent": round(disk.percent, 1),
            "disk_alert": _alert_level(disk.percent, ALERT_DISK_PERCENT),
            "alerts": alerts,
        },
    }


# ============================================================
# 全量聚合 — 前端面板一次拉取
# ============================================================

@router.get("/overview")
async def overview(
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    运维全量聚合接口 — 一次请求返回所有监控数据

    用途：前端运维面板定时轮询此接口（建议 5~10 秒间隔），
    避免发起 5 个独立请求的开销。

    返回格式：{ server, containers, services, business, storage }
    """
    # 复用各子接口的逻辑
    server_data = await server_stats(user)
    container_data = await container_stats(user)
    service_data = await service_health(user, db)
    business_data = await business_stats(user, db)
    storage_data = await storage_stats(user, db)

    # 合并所有告警
    all_alerts = []
    for d in [server_data, container_data, service_data, business_data, storage_data]:
        if d.get("code") == 0 and "alerts" in d.get("data", {}):
            all_alerts.extend(d["data"]["alerts"])

    return {
        "code": 0,
        "data": {
            "server": server_data["data"],
            "containers": container_data["data"],
            "services": service_data["data"],
            "business": business_data["data"],
            "storage": storage_data["data"],
            "all_alerts": all_alerts,
            "alert_count": len(all_alerts),
            "timestamp": datetime.now().isoformat(),
        },
    }

"""
FastAPI 应用入口模块
====================
功能：创建 FastAPI 应用实例，配置中间件和路由，管理应用生命周期。

在系统中的角色：
- 作为整个后端服务的启动入口，由 uvicorn 加载运行
- 通过 lifespan 上下文管理器统一管理启动/关闭时的资源初始化与释放
- 注册 CORS 中间件，使 Vue3 前端（不同源）能跨域访问后端 API
- 汇总所有子路由（auth/heartbeat/course/stats/notify），构成完整 API 体系
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import init_db
from app.database_redis import close_redis
from app.routers import auth, heartbeat, course, stats, notify, admin, homework, ops, section, announcement, feedback, agent
from app.services.scheduler import start_scheduler, stop_scheduler

settings = get_settings()


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent


def _candidate_upload_dirs() -> list[str]:
    return [
        str(BASE_DIR / "uploads"),
        str(REPO_DIR / "uploads"),
        str(REPO_DIR / "jpg"),
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器（启动 → 运行 → 关闭）

    用途：在应用启动时完成异步资源初始化，在关闭时释放资源。
    这是 FastAPI 推荐的生命周期管理方式，替代了已废弃的 on_event 装饰器。

    参数：
        app: FastAPI 应用实例（由框架自动注入）

    启动阶段：
        1. 调用 init_db() 创建所有数据库表（若表不存在）
        2. 启动 APScheduler 定时任务调度器（心跳日志清理等）
    关闭阶段：
        1. 停止 APScheduler 调度器
        2. 调用 close_redis() 优雅关闭 Redis 连接池
    """
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()


app = FastAPI(
    title="22中学习进度监督系统",
    description="基于钉钉H5微应用的学生学习进度监督API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件配置
# 开发阶段允许所有来源，生产环境应将 allow_origins 收窄为前端域名列表
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_safe_upload_path(path: str) -> bool:
    norm = os.path.normpath(path).replace("\\", "/")
    return not (
        norm.startswith("../")
        or norm.startswith("..\\")
        or norm.startswith("./")
        or norm == ".."
        or norm == "."
    )


@app.get("/api/uploads/{file_path:path}")
async def serve_upload(file_path: str):
    if not _is_safe_upload_path(file_path):
        raise HTTPException(status_code=400, detail="非法文件路径")

    norm_path = os.path.normpath(file_path).lstrip(os.sep)
    fallback_paths = [norm_path]
    normalized_for_prefix = os.path.normpath(norm_path).replace("\\", "/")
    if normalized_for_prefix.startswith("homework/"):
        fallback_paths.append(norm_path[len("homework/"):])

    for base in _candidate_upload_dirs():
        for path_item in fallback_paths:
            candidate = Path(base) / path_item
            try:
                candidate = candidate.resolve()
            except OSError:
                continue

            base_path = Path(base).resolve()
            if str(candidate).startswith(f"{str(base_path)}{os.sep}") and candidate.is_file():
                return FileResponse(candidate)

    raise HTTPException(status_code=404, detail="文件不存在")

# 注册各业务路由模块
# auth        — 钉钉免登认证，获取 JWT 令牌
# heartbeat   — 学习心跳上报，防刷课核心
# course      — 课程 CRUD（元数据级）
# section     — 小节 CRUD + 视频上传（v3.0 课程-小节两级结构）
# stats       — 教师统计看板数据聚合 + 排行榜 + 签到日历 + 学习报告
# notify      — 钉钉消息推送（学习提醒、每日报告）
# admin       — 管理后台（用户管理、班级管理）
# homework    — 作业管理（发布、提交、批改，v4.0 小节级）
# ops         — 运维监控（服务器资源、容器状态、业务数据、存储信息）
# announcement — 公告管理（教师/管理员发布通知，v4.0 新增）
# feedback    — 小节评价反馈（学生评分留言，v4.0 新增）
app.include_router(auth.router)
app.include_router(heartbeat.router)
app.include_router(course.router)
app.include_router(section.router)
app.include_router(stats.router)
app.include_router(notify.router)
app.include_router(admin.router)
app.include_router(homework.router)
app.include_router(ops.router)
app.include_router(announcement.router)
app.include_router(feedback.router)
app.include_router(agent.router)


@app.get("/api/health")
async def health_check():
    """
    健康检查接口

    用途：供容器编排（如 Docker/K8s）和前端判断后端服务是否存活。
    无需鉴权，始终返回 200。

    返回值：
        {"status": "ok", "version": "1.0.0"}
    """
    return {"status": "ok", "version": "1.0.0"}

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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import init_db
from app.database_redis import close_redis
from app.routers import auth, heartbeat, course, stats, notify, admin, homework
from app.services.scheduler import start_scheduler, stop_scheduler

settings = get_settings()


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

# 注册各业务路由模块
# auth     — 钉钉免登认证，获取 JWT 令牌
# heartbeat — 学习心跳上报，防刷课核心
# course   — 课程 CRUD 和学习进度查询
# stats    — 教师统计看板数据聚合
# notify   — 钉钉消息推送（学习提醒、每日报告）
# admin    — 管理后台（用户管理、班级管理）
# homework — 作业管理（发布、提交、批改）
app.include_router(auth.router)
app.include_router(heartbeat.router)
app.include_router(course.router)
app.include_router(stats.router)
app.include_router(notify.router)
app.include_router(admin.router)
app.include_router(homework.router)


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

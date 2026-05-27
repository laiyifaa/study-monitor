from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import init_db
from app.routers import auth, heartbeat

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化数据库表
    await init_db()
    yield


app = FastAPI(
    title="22中学习进度监督系统",
    description="基于钉钉H5微应用的学生学习进度监督API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(heartbeat.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

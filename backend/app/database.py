"""
数据库引擎与会话管理模块
========================
功能：创建 SQLAlchemy 异步引擎，提供数据库会话和 ORM 基类。

在系统中的角色：
- 为所有数据模型提供 Base 基类，模型继承 Base 即可映射到数据库表
- 为所有路由提供 get_db 依赖注入函数，确保每次请求获取独立的数据库会话
- 提供 init_db 函数，在应用启动时自动创建所有表（开发阶段快捷建表）

设计决策：
- 使用 aiomysql 异步驱动，因整个 FastAPI 应用是异步架构，
  同步驱动会阻塞事件循环，导致并发性能骤降
- expire_on_commit=False 避免提交后访问属性触发延迟加载（异步环境下会报错）
- 连接池 pool_size=20 + max_overflow=10，适合校园场景的适中并发量
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# 异步数据库引擎
# echo=settings.DEBUG — 开发模式打印 SQL，生产模式静默，兼顾调试与性能
# pool_size=20 — 常驻连接数，覆盖日常高峰并发
# max_overflow=10 — 突发流量时额外创建的连接，超出则排队等待
engine = create_async_engine(settings.mysql_url, echo=settings.DEBUG, pool_size=20, max_overflow=10)

# 异步会话工厂
# expire_on_commit=False — 提交后对象属性不过期，避免异步环境下触发隐式同步查询报错
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """
    ORM 声明式基类

    用途：所有数据模型（User/Course/StudySession/HeartbeatLog）继承此基类，
         Base.metadata 收集所有模型的表定义，供 init_db 统一建表使用。
    """
    pass


async def get_db() -> AsyncSession:
    """
    获取数据库会话（依赖注入用）

    用途：作为 FastAPI 的 Depends 依赖，在每个请求中自动获取一个数据库会话，
         请求结束后自动关闭，确保连接回归连接池。

    参数：无（FastAPI 自动注入）

    返回值：yield 一个 AsyncSession 实例

    核心逻辑：
        1. async_session() 创建新会话
        2. try/yield/finally 确保无论路由是否抛异常，会话都会被 close()
        3. close() 将连接归还连接池而非销毁，避免频繁创建 TCP 连接
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    初始化数据库表

    用途：在应用启动时（lifespan 中）调用，自动创建所有不存在的数据表。

    核心逻辑：
        1. engine.begin() 开启一个事务
        2. run_sync 因为 Base.metadata.create_all 是同步方法，
           需要通过 run_sync 在异步上下文中执行
        3. 只创建不存在的表，已有表不会被修改（生产环境应用 Alembic 迁移）
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        answer_files_exists = await conn.scalar(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'assignments' "
            "AND column_name = 'answer_files'"
        ))
        if not answer_files_exists:
            await conn.execute(text(
                "ALTER TABLE assignments "
                "ADD COLUMN answer_files TEXT NULL COMMENT '答案附件URL数组(JSON)' AFTER question_files"
            ))

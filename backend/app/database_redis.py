"""
Redis 异步客户端模块
====================
功能：提供全局 Redis 异步客户端的单例管理，支持延迟初始化和优雅关闭。

在系统中的角色：
- 缓存钉钉 access_token：钉钉 API 返回的 token 有效期 2 小时，
  缓存到 Redis 避免每次请求都重新获取，提升响应速度并避免触发限流
- 心跳限流：利用 Redis 的原子递增操作，限制每个学生每 30 秒只能上报一次心跳，
  防止恶意刷请求或客户端 bug 导致的心跳风暴

设计决策：
- 延迟初始化（Lazy Init）：不模块加载时建连，而是首次调用 get_redis() 时才建立。
  原因是模块加载阶段 Redis 可能尚未就绪（如 Docker 中容器启动顺序不确定），
  若在此阶段就建连会导致整个应用无法启动
- decode_responses=True：自动将 Redis 返回的 bytes 解码为 str，
  省去每个调用点手动 decode 的繁琐
- 全局单例：通过 _redis 模块变量 + 判空逻辑实现，而非 lru_cache，
  因为 Redis 实例不能被 pickle 序列化
"""

import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

# 全局 Redis 实例，初始为 None，首次调用 get_redis() 时按需创建
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    获取 Redis 异步客户端单例

    用途：供路由和业务模块调用，获取一个可复用的 Redis 连接。
          首次调用时自动创建连接，后续调用直接返回已有实例。

    参数：无

    返回值：aioredis.Redis 实例

    核心逻辑：
        1. 检查 _redis 是否已初始化
        2. 若未初始化，根据配置创建连接：
           - socket_timeout=5 — 读写超时 5 秒，避免单次操作无限阻塞
           - socket_connect_timeout=3 — 连接超时 3 秒，快速发现 Redis 不可达
           - retry_on_timeout=True — 超时后自动重试，提升网络抖动场景的鲁棒性
        3. 返回连接实例
    """
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=3,
            retry_on_timeout=True,
        )
    return _redis


async def close_redis():
    """
    关闭 Redis 连接池

    用途：在应用关闭时（lifespan 的清理阶段）调用，
         优雅关闭所有连接，防止连接泄漏。

    核心逻辑：
        1. 检查 _redis 是否存在（可能从未初始化）
        2. close() 关闭连接池中所有连接
        3. 将 _redis 置为 None，允许后续重新初始化（如测试场景）
    """
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None

"""Redis 客户端 - 用于 access_token 缓存和心跳限流"""
import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

# 延迟初始化，避免启动时 Redis 不可用导致整个应用无法启动
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
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
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None

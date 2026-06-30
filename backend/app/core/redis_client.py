from redis.asyncio import Redis, ConnectionPool
from app.config import get_settings

settings = get_settings()
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return _pool


async def get_redis() -> Redis:
    return Redis(connection_pool=get_pool())

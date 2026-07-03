"""
Redis-backed sliding-window rate limiter for auth endpoints.

Fails OPEN: if Redis is unreachable we let the request through — auth must
not go down because the cache did.
"""
import time
import logging
from fastapi import HTTPException, Request

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


def client_ip(request: Request) -> str:
    """Client IP, honoring the first X-Forwarded-For hop (reverse proxy)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """
    Sliding-window limit: at most `limit` events per `window_seconds` for `key`.
    Raises 429 when exceeded.
    """
    now = time.time()
    redis_key = f"ratelimit:{key}"
    try:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {f"{now}": now})
        pipe.expire(redis_key, window_seconds)
        results = await pipe.execute()
        count = results[1]
    except Exception as exc:  # Redis down — fail open
        logger.warning("rate limiter unavailable (%s), allowing request", exc)
        return

    if count >= limit:
        retry_after = window_seconds
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": str(retry_after)},
        )

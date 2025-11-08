import json
import os
import uuid
from typing import Optional, Tuple

import redis.asyncio as redis
from fastapi import HTTPException, Request, Response

from app.models import User
from app.utils.env import get_env_int, get_env_str

RedisClient = redis.Redis

_session_client: Optional[RedisClient] = None
SESSION_COOKIE_NAME = "session_id"
SESSION_PREFIX = "session:"
SESSION_TTL = int(os.getenv("SESSION_TTL", "86400"))


def _generate_username(user_id: int) -> str:
    return f"Player{user_id}"


async def get_redis_client() -> RedisClient:
    """Return a singleton Redis client instance."""
    global _session_client
    if _session_client is None:
        try:
            _session_client = redis.Redis(
                host=get_env_str("REDIS_HOST", "redis"),
                port=get_env_int("REDIS_PORT", 6379),
                db=get_env_int("REDIS_DB", 0),
                decode_responses=False,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            await _session_client.ping()
        except Exception as e:
            import logging
            log = logging.getLogger("app.dependencies")
            log.warning("⚠️ Redis connection failed: %s. Will retry on first use.", e)
            # Create client anyway - it will retry on first use
            _session_client = redis.Redis(
                host=get_env_str("REDIS_HOST", "redis"),
                port=get_env_int("REDIS_PORT", 6379),
                db=get_env_int("REDIS_DB", 0),
                decode_responses=False,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
                health_check_interval=30,
            )
    return _session_client


async def get_or_create_session(
    response: Response,
    redis_client: RedisClient,
    request: Optional[Request] = None,
) -> Tuple[str, User]:
    """Retrieve existing session or create a new one."""
    session_id: Optional[str] = None

    if request:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if session_id:
        session_key = f"{SESSION_PREFIX}{session_id}"
        existing = await redis_client.get(session_key)
        if existing:
            data = json.loads(existing)
            user = User(
                id=data["user_id"],
                username=data.get("username"),
                telegram_id=data.get("telegram_id"),
            )
            await redis_client.expire(session_key, SESSION_TTL)
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=session_id,
                max_age=SESSION_TTL,
                httponly=True,
                samesite="lax",
            )
            return session_id, user

    session_id = str(uuid.uuid4())
    user_id = uuid.uuid4().int % 1_000_000_000
    user = User(id=user_id, username=_generate_username(user_id), telegram_id=None)

    session_data = {
        "user_id": user.id,
        "username": user.username,
        "telegram_id": user.telegram_id,
    }

    session_key = f"{SESSION_PREFIX}{session_id}"
    await redis_client.set(session_key, json.dumps(session_data), ex=SESSION_TTL)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
    )

    return session_id, user


async def get_current_user(request: Request) -> User:
    """Fetch the current user from the session cookie."""
    redis_client = await get_redis_client()
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session_key = f"{SESSION_PREFIX}{session_id}"
    session_data = await redis_client.get(session_key)

    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    data = json.loads(session_data)
    user = User(
        id=data["user_id"],
        username=data.get("username"),
        telegram_id=data.get("telegram_id"),
    )

    return user

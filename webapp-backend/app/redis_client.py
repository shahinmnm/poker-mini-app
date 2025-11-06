import redis
from typing import Optional

from app.utils.env import get_env_int, get_env_str

# استفاده از Redis client سازگار با ورژن 4.5.4
redis_client: Optional[redis.Redis] = None

def get_redis_client() -> redis.Redis:
    """Get Redis client instance (singleton pattern)."""
    global redis_client
    
    if redis_client is None:
        redis_client = redis.Redis(
            host=get_env_str("REDIS_HOST", "localhost"),
            port=get_env_int("REDIS_PORT", 6379),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )
    
    return redis_client

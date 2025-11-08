from fastapi import APIRouter
from app.dependencies import get_redis_client

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """Check API and Redis health."""
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        redis_status = "ok"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    return {
        "status": "ok",
        "redis": redis_status,
        "version": "1.0.0"
    }

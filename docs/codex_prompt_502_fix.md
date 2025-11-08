# Codex Prompt: Fix 502 Error in Telegram Mini-App

## Context
A FastAPI Telegram mini-app backend is returning 502 errors through nginx. The backend runs in Docker with Redis, and nginx proxies `/api/*` requests to the FastAPI backend.

## Critical Bugs to Fix

### Bug 1: Redis Client Type Mismatch in Health Route
**File**: `webapp-backend/app/routes/health.py`
**Issue**: Uses synchronous `redis.Redis` client in an async FastAPI route handler, causing blocking operations that can hang or fail.

**Current Code**:
```python
from app.redis_client import get_redis_client  # SYNC client

@router.get("/health")
async def health_check():
    redis_client = get_redis_client()  # Blocking call!
    redis_client.ping()  # Blocking in async context
```

**Required Fix**:
- Import async Redis client from `app.dependencies`
- Make Redis operations properly async with `await`
- Handle Redis connection failures gracefully (don't crash if Redis is down)

### Bug 2: Health Route Not Registered
**File**: `webapp-backend/app/main.py`
**Issue**: `app/routes/health.py` exists but is never imported or included in the FastAPI app.

**Required Fix**:
- Either import and register the health router, OR
- Remove the unused health.py file and keep the simple health route in main.py
- Ensure health endpoint is accessible at both `/health` and `/api/health`

### Bug 3: Inconsistent Redis Client Usage
**Files**: Multiple files use different Redis clients
**Issue**: 
- `app/dependencies.py` uses `redis.asyncio` (async) ✅
- `app/redis_client.py` uses `redis` (sync) ❌
- Some routes use sync, some use async

**Required Fix**:
- Standardize on async Redis client from `app.dependencies`
- Update all imports to use the async client
- Remove or deprecate the sync client

### Bug 4: Nginx Proxy Configuration
**File**: `webapp-frontend/nginx.conf`
**Issue**: Proxy configuration might have path forwarding issues.

**Current**:
```nginx
location /api/ {
    proxy_pass http://webapp_api_upstream;
}
```

**Required Fix**:
- Ensure proxy_pass correctly forwards paths
- Add proper error handling
- Verify upstream is reachable

## Implementation Requirements

1. **All Redis operations must be async** - use `await` for all Redis calls
2. **Health check must be resilient** - return partial status if Redis is unavailable
3. **Backend must start successfully** - handle missing optional dependencies gracefully
4. **Consistent error handling** - log errors but don't crash the app
5. **Proper logging** - add debug logs for connection attempts

## Expected Behavior After Fix

- Backend starts successfully and listens on port 8000
- Health endpoint `/api/health` returns `{"status": "ok", ...}` even if Redis is temporarily down
- Nginx can successfully proxy requests to backend
- No 502 errors from nginx
- All routes use async Redis client consistently

## Testing Checklist

After fixes:
- [ ] Backend container starts without errors
- [ ] Health endpoint responds: `curl http://localhost:8000/api/health`
- [ ] Health endpoint works from nginx: `curl http://localhost/api/health`
- [ ] Redis connection works (if Redis is available)
- [ ] No blocking operations in async routes
- [ ] All imports resolve correctly

## Code Changes Needed

1. Fix `webapp-backend/app/routes/health.py` to use async Redis
2. Update `webapp-backend/app/main.py` to register health route (or remove unused file)
3. Update any files importing from `app.redis_client` to use `app.dependencies` instead
4. Verify nginx configuration is correct
5. Add error handling for Redis connection failures

Fix these issues systematically, ensuring backward compatibility and proper async patterns.

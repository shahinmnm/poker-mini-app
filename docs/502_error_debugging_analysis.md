# 502 Error Debugging Analysis & Codex Prompt

## 🔍 Root Cause Analysis

After deep analysis of your Telegram mini-app codebase, I've identified **multiple critical issues** that could cause nginx 502 errors:

### **Critical Issues Found:**

#### 1. **Redis Client Type Mismatch** ⚠️ CRITICAL
- **Location**: `webapp-backend/app/routes/health.py` (line 2, 10)
- **Problem**: Uses **synchronous** Redis client (`redis.Redis`) in an **async** FastAPI route
- **Impact**: This will cause the health check to fail or hang, preventing nginx from detecting a healthy backend
- **Code**:
  ```python
  # health.py line 2
  from app.redis_client import get_redis_client  # SYNC client
  
  # health.py line 10
  redis_client = get_redis_client()  # Called in async function!
  redis_client.ping()  # Blocking call in async context
  ```

#### 2. **Health Route Not Imported** ⚠️ CRITICAL
- **Location**: `webapp-backend/app/main.py`
- **Problem**: `app/routes/health.py` exists but is **never imported** or registered
- **Impact**: The health check endpoint might not work as expected
- **Current**: Only the simple health route in `main.py` (line 49) is registered

#### 3. **Dual Redis Client Implementations** ⚠️ HIGH
- **Problem**: Two different Redis clients exist:
  - `app/dependencies.py`: Uses `redis.asyncio` (async) ✅
  - `app/redis_client.py`: Uses `redis` (sync) ❌
- **Impact**: Inconsistent Redis access patterns, potential blocking issues

#### 4. **Nginx Proxy Configuration** ⚠️ MEDIUM
- **Location**: `webapp-frontend/nginx.conf` line 50
- **Potential Issue**: `proxy_pass http://webapp_api_upstream;` without trailing slash
- **Impact**: Path forwarding might be incorrect in some edge cases
- **Note**: This should work, but needs verification

#### 5. **Backend Startup Dependencies** ⚠️ MEDIUM
- **Problem**: Backend might fail to start if:
  - Redis is not accessible (`REDIS_HOST` env var incorrect)
  - Import errors during startup
  - Missing environment variables

---

## 🧪 Debugging Steps to Run on VPS

Run these commands on your VPS to diagnose the exact issue:

### **Step 1: Check Backend Container Status**
```bash
docker-compose ps webapp-api
docker-compose logs webapp-api --tail=100
```

### **Step 2: Check if Backend is Listening**
```bash
# From inside the webapp-frontend container
docker-compose exec webapp-frontend wget -O- http://webapp-api:8000/health

# Or from host
docker-compose exec webapp-api wget -O- http://localhost:8000/health
```

### **Step 3: Check Nginx Error Logs**
```bash
docker-compose logs webapp-frontend | grep -i error
docker-compose exec webapp-frontend cat /var/log/nginx/error.log
```

### **Step 4: Test Backend Directly**
```bash
# Test health endpoint
docker-compose exec webapp-api curl http://localhost:8000/health
docker-compose exec webapp-api curl http://localhost:8000/api/health

# Test Redis connection
docker-compose exec webapp-api python -c "import redis; r=redis.Redis(host='redis', port=6379); print(r.ping())"
```

### **Step 5: Check Environment Variables**
```bash
docker-compose exec webapp-api env | grep -E "(REDIS|WEBAPP|TELEGRAM)"
```

### **Step 6: Test Nginx Proxy**
```bash
# From frontend container
docker-compose exec webapp-frontend curl http://localhost/api/health
docker-compose exec webapp-frontend curl -v http://webapp-api:8000/health
```

---

## 📋 Expected Outputs

### ✅ **Healthy Backend Should Return:**
```json
{"status": "ok", "time": "2024-..."}
```

### ❌ **If Backend is Down:**
- `502 Bad Gateway` from nginx
- Connection refused errors in logs

### ❌ **If Redis Connection Fails:**
- Backend might start but health check fails
- Errors in backend logs about Redis connection

---

## 🔧 Codex Prompt to Fix Issues

Copy this prompt to Codex/Claude to fix all issues:

---

**CODEX PROMPT START:**

```
You are fixing critical bugs in a FastAPI Telegram mini-app backend that's causing nginx 502 errors.

CRITICAL FIXES NEEDED:

1. Fix Redis client mismatch in health.py:
   - File: webapp-backend/app/routes/health.py
   - Problem: Uses synchronous redis.Redis in async FastAPI route
   - Solution: Change to use async redis client from app.dependencies.get_redis_client
   - Make the health_check function properly async and await Redis operations

2. Register health route in main.py:
   - File: webapp-backend/app/main.py
   - Problem: app/routes/health.py exists but is never imported
   - Solution: Import and include the health router at /api/health (or keep existing simple one, but fix Redis issue)

3. Consolidate Redis clients:
   - Remove or fix app/redis_client.py to use async client
   - Ensure all routes use async Redis client from app.dependencies

4. Fix nginx proxy_pass configuration:
   - File: webapp-frontend/nginx.conf
   - Ensure proxy_pass correctly forwards /api/* requests to backend
   - Add proper error handling and timeouts

5. Add better error handling:
   - Make health check resilient to Redis failures (don't crash if Redis is down)
   - Add startup checks for required environment variables
   - Improve logging for debugging

REQUIREMENTS:
- All Redis operations must be async
- Health check should work even if Redis is temporarily unavailable
- Backend must start successfully even with missing optional dependencies
- All routes must use consistent async Redis client
- Fix any import errors or circular dependencies

Please fix these issues systematically, ensuring:
- Backward compatibility where possible
- Proper async/await patterns
- Error handling that doesn't crash the app
- Clear logging for debugging
```

**CODEX PROMPT END**

---

## 🎯 Quick Fix Summary

The **most likely cause** of your 502 error is:

1. **Backend crashing on startup** due to Redis connection issues or import errors
2. **Health check failing** due to sync Redis call in async context
3. **Nginx unable to connect** to backend because backend isn't listening on port 8000

**Immediate actions:**
1. Run the debugging commands above to identify the exact failure point
2. Fix the Redis client mismatch in `health.py`
3. Ensure backend starts successfully and listens on port 8000
4. Verify nginx can reach the backend container

---

## 📝 Additional Notes

- The docker-compose healthcheck uses `127.0.0.1:8000` which should work from inside the container
- The backend exposes port 8000 internally (not to host)
- Nginx connects via Docker network using service name `webapp-api:8000`
- Ensure `REDIS_HOST=redis` (service name) in docker-compose environment

---

**Next Steps:**
1. Run debugging commands and share outputs
2. Apply fixes using the Codex prompt
3. Test each fix incrementally
4. Monitor logs during deployment

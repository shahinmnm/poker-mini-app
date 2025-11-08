#!/bin/bash
# Debugging script for 502 error diagnosis
# Run this on your VPS to identify the exact issue

set -e

echo "🔍 502 Error Diagnostic Script"
echo "================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
    fi
}

# 1. Check if docker-compose is running
echo "1. Checking Docker Compose status..."
if docker-compose ps > /dev/null 2>&1; then
    print_status 0 "Docker Compose is accessible"
else
    print_status 1 "Docker Compose not found or not accessible"
    exit 1
fi

# 2. Check container status
echo ""
echo "2. Checking container status..."
docker-compose ps

# 3. Check backend container
echo ""
echo "3. Checking webapp-api container..."
if docker-compose ps webapp-api | grep -q "Up"; then
    print_status 0 "webapp-api container is running"
else
    print_status 1 "webapp-api container is NOT running"
    echo "Recent logs:"
    docker-compose logs webapp-api --tail=50
fi

# 4. Check frontend container
echo ""
echo "4. Checking webapp-frontend container..."
if docker-compose ps webapp-frontend | grep -q "Up"; then
    print_status 0 "webapp-frontend container is running"
else
    print_status 1 "webapp-frontend container is NOT running"
fi

# 5. Check Redis container
echo ""
echo "5. Checking Redis container..."
if docker-compose ps redis | grep -q "Up"; then
    print_status 0 "Redis container is running"
    
    # Test Redis connection
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        print_status 0 "Redis is responding to ping"
    else
        print_status 1 "Redis is not responding to ping"
    fi
else
    print_status 1 "Redis container is NOT running"
fi

# 6. Check backend health endpoint directly
echo ""
echo "6. Testing backend health endpoint (direct)..."
if docker-compose exec -T webapp-api curl -s http://localhost:8000/health > /dev/null 2>&1; then
    RESPONSE=$(docker-compose exec -T webapp-api curl -s http://localhost:8000/health)
    print_status 0 "Backend health endpoint responds"
    echo "Response: $RESPONSE"
else
    print_status 1 "Backend health endpoint NOT responding"
    echo "Backend logs:"
    docker-compose logs webapp-api --tail=30
fi

# 7. Check backend API health endpoint
echo ""
echo "7. Testing backend /api/health endpoint (direct)..."
if docker-compose exec -T webapp-api curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    RESPONSE=$(docker-compose exec -T webapp-api curl -s http://localhost:8000/api/health)
    print_status 0 "Backend /api/health endpoint responds"
    echo "Response: $RESPONSE"
else
    print_status 1 "Backend /api/health endpoint NOT responding"
fi

# 8. Check nginx proxy
echo ""
echo "8. Testing nginx proxy to backend..."
if docker-compose exec -T webapp-frontend curl -s http://webapp-api:8000/health > /dev/null 2>&1; then
    RESPONSE=$(docker-compose exec -T webapp-frontend curl -s http://webapp-api:8000/health)
    print_status 0 "Nginx can reach backend via Docker network"
    echo "Response: $RESPONSE"
else
    print_status 1 "Nginx CANNOT reach backend via Docker network"
fi

# 9. Check nginx public endpoint
echo ""
echo "9. Testing nginx public /api/health endpoint..."
if docker-compose exec -T webapp-frontend curl -s http://localhost/api/health > /dev/null 2>&1; then
    RESPONSE=$(docker-compose exec -T webapp-frontend curl -s http://localhost/api/health)
    print_status 0 "Nginx public /api/health endpoint responds"
    echo "Response: $RESPONSE"
else
    print_status 1 "Nginx public /api/health endpoint NOT responding"
    echo "Nginx error logs:"
    docker-compose exec webapp-frontend cat /var/log/nginx/error.log 2>/dev/null || echo "No error log found"
fi

# 10. Check environment variables
echo ""
echo "10. Checking critical environment variables..."
ENV_VARS=$(docker-compose exec -T webapp-api env | grep -E "(REDIS_HOST|REDIS_PORT|WEBAPP|TELEGRAM)" || true)
if [ -n "$ENV_VARS" ]; then
    echo "$ENV_VARS"
else
    print_status 1 "No environment variables found (this might be normal)"
fi

# 11. Check backend logs for errors
echo ""
echo "11. Recent backend errors (last 20 lines)..."
docker-compose logs webapp-api --tail=20 | grep -i error || echo "No errors found in recent logs"

# 12. Check nginx logs for errors
echo ""
echo "12. Recent nginx errors..."
docker-compose logs webapp-frontend --tail=20 | grep -i error || echo "No errors found in recent logs"

# Summary
echo ""
echo "================================"
echo "📊 Diagnostic Summary"
echo "================================"
echo ""
echo "If you see ❌ errors above, those are the issues to fix."
echo ""
echo "Common issues and solutions:"
echo "1. Backend not running → Check docker-compose logs webapp-api"
echo "2. Redis connection failed → Check REDIS_HOST env var (should be 'redis')"
echo "3. Nginx 502 → Backend is down or not accessible"
echo "4. Health check fails → Check Redis connection and async Redis client usage"
echo ""
echo "After applying fixes, rebuild containers:"
echo "  docker-compose down"
echo "  docker-compose build webapp-api webapp-frontend"
echo "  docker-compose up -d"
echo ""

# webapp-backend/app/main.py
from __future__ import annotations

import os
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger("app.main")
logging.basicConfig(level=logging.INFO)

# ---- CORS ----
DEFAULT_ALLOWED_ORIGINS = [
    "https://poker.shahin8n.sbs",
    "https://t.me",
    "https://web.telegram.org",
]

cors_origins_env = os.getenv("CORS_ORIGINS", "")
extra_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
CORS_ORIGINS: List[str] = list(dict.fromkeys(DEFAULT_ALLOWED_ORIGINS + extra_origins))

app = FastAPI(title="Poker WebApp API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "X-Telegram-Init-Data", "Content-Type"],
    allow_credentials=True,
)

log.info("🚀 Poker WebApp API starting...")
log.info("📍 CORS origins: %s", CORS_ORIGINS)

# ---- Auth helpers ----
from app.auth import UserContext, create_user_jwt, require_telegram_user

# ---- Mock data ----
MOCK_TABLES = [
    {"id": "pub-1", "name": "Main Lobby", "stakes": "50/100", "players_count": 5, "max_players": 9, "is_private": False, "status": "waiting"},
    {"id": "pub-2", "name": "Turbo Sit&Go", "stakes": "100/200", "players_count": 9, "max_players": 9, "is_private": False, "status": "running"},
    {"id": "grp-777", "name": "Friends Table", "stakes": "10/20", "players_count": 3, "max_players": 6, "is_private": True, "status": "waiting"},
]

# ---- Core router (mounted at / and /api) ----
router = APIRouter()

@router.get("/health")
def health() -> Dict[str, Any]:
    from datetime import datetime, timezone
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

@router.get("/tables")
def list_tables() -> Dict[str, Any]:
    return {"tables": MOCK_TABLES}

@router.post("/tables/{table_id}/join")
def join_table(table_id: str, user: UserContext = Depends(require_telegram_user)) -> Dict[str, Any]:
    exists = any(t["id"] == table_id for t in MOCK_TABLES)
    if not exists:
        raise HTTPException(status_code=404, detail="Table not found")
    return {"ok": True, "joined": True, "table_id": table_id, "user_id": user.id}

@router.get("/user/settings")
def user_settings(user: UserContext = Depends(require_telegram_user)) -> Dict[str, Any]:
    return {
        "user_id": user.id,
        "theme": "auto",
        "notifications": True,
        "locale": "en",
        "currency": "chips",
        "experimental": False,
    }

@router.get("/user/stats")
def user_stats(user: UserContext = Depends(require_telegram_user)) -> Dict[str, Any]:
    from datetime import datetime, timezone
    return {
        "user_id": user.id,
        "hands_played": 124,
        "biggest_win": 15200,
        "biggest_loss": -4800,
        "win_rate": 0.56,
        "last_played": datetime.now(timezone.utc).isoformat(),
        "streak_days": 3,
        "chip_balance": 25000,
        "rank": "Rising Shark",
    }


@router.post("/auth/exchange")
def exchange_token(user: UserContext = Depends(require_telegram_user)) -> Dict[str, Any]:
    token = create_user_jwt(user)
    return {"token": token, "expires_in": int(os.getenv("TELEGRAM_JWT_TTL", "900"))}

# Mount once at / and once at /api (so both work)
app.include_router(router)
app.include_router(router, prefix="/api")

# Include group game routes
try:
    from app.routes import group_game
    app.include_router(group_game.router, prefix="/api")
    log.info("✅ Group game routes registered")
except Exception as e:
    log.warning("⚠️ Could not load group game routes: %s", e)


# ---- Startup log of routes (for your diagnostics) ----
@app.on_event("startup")
async def show_routes():
    log.info("📡 Routes registered:")
    for r in app.router.routes:
        methods = getattr(r, "methods", {"GET"})
        path = getattr(r, "path", "")
        log.info("  %s %s", methods, path)

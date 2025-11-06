"""API routes for group game management."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_redis_client
from app.models import User
from app.services.bot_service import get_bot_service
from fastapi import Request
from typing import Union

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/group-game", tags=["group-game"])

# Redis keys
GROUP_GAME_PREFIX = "group_game:"
GROUP_GAME_META_PREFIX = "group_game_meta:"
GROUP_GAME_PLAYERS_PREFIX = "group_game_players:"


async def get_user_from_request(request: Request) -> User:
    """
    Get user from request - supports both session-based and simple identity auth.
    """
    # Try session-based auth first (from dependencies)
    try:
        from app.dependencies import get_current_user
        return await get_current_user(request)
    except Exception:
        pass
    
    # Fallback to simple identity from query/header
    user_id = request.query_params.get("user_id")
    if not user_id:
        # Try to get from header
        auth_header = request.headers.get("X-Telegram-Init-Data")
        if auth_header:
            # Parse initData to get user_id (simplified)
            try:
                from urllib.parse import parse_qsl
                parsed = dict(parse_qsl(auth_header))
                user_json = parsed.get("user", "{}")
                import json
                user_obj = json.loads(user_json)
                user_id = user_obj.get("id")
            except Exception:
                pass
    
    if user_id:
        return User(id=int(user_id), username=f"Player{user_id}", telegram_id=int(user_id))
    
    raise HTTPException(status_code=401, detail="Authentication required")


class StartGroupGameRequest(BaseModel):
    """Request to start a group game."""

    chat_id: int
    miniapp_url: Optional[str] = None


class GroupGameInfo(BaseModel):
    """Group game information."""

    game_id: str
    chat_id: int
    initiator_id: int
    initiator_name: str
    players: List[Dict[str, Any]]
    message_id: Optional[int] = None
    status: str  # "waiting", "starting", "active"
    created_at: str
    min_players: int = 2


class JoinGroupGameRequest(BaseModel):
    """Request to join a group game."""

    game_id: str
    user_name: Optional[str] = None


@router.post("/start", response_model=GroupGameInfo)
async def start_group_game(
    request: StartGroupGameRequest,
    http_request: Request,
    user: User = Depends(get_user_from_request),
    redis=Depends(get_redis_client),
) -> GroupGameInfo:
    """
    Start a new group game and send invite message to Telegram group.

    This creates a game lobby in the group and sends a message with join buttons.
    """
    try:
        # Generate unique game ID
        game_id = f"grp_{uuid.uuid4().hex[:12]}"

        # Store game metadata
        game_meta = {
            "game_id": game_id,
            "chat_id": request.chat_id,
            "initiator_id": user.id,
            "initiator_name": user.username or f"Player{user.id}",
            "status": "waiting",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "min_players": 2,
            "message_id": None,
        }

        # Initialize players list with initiator
        players = [
            {
                "id": user.id,
                "name": user.username or f"Player{user.id}",
                "joined_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        # Store in Redis
        await redis.setex(
            f"{GROUP_GAME_META_PREFIX}{game_id}",
            3600,  # 1 hour TTL
            json.dumps(game_meta),
        )
        await redis.setex(
            f"{GROUP_GAME_PLAYERS_PREFIX}{game_id}",
            3600,
            json.dumps(players),
        )

        # Send invite message to group via bot
        bot_service = get_bot_service()
        miniapp_url = request.miniapp_url or os.getenv(
            "MINIAPP_URL", "https://your-miniapp-url.com"
        )
        message_id = await bot_service.send_group_game_invite(
            chat_id=request.chat_id,
            initiator_name=game_meta["initiator_name"],
            game_id=game_id,
            miniapp_url=miniapp_url,
        )

        if message_id:
            game_meta["message_id"] = message_id
            await redis.setex(
                f"{GROUP_GAME_META_PREFIX}{game_id}",
                3600,
                json.dumps(game_meta),
            )

        return GroupGameInfo(
            game_id=game_id,
            chat_id=request.chat_id,
            initiator_id=user.id,
            initiator_name=game_meta["initiator_name"],
            players=players,
            message_id=message_id,
            status="waiting",
            created_at=game_meta["created_at"],
            min_players=2,
        )

    except Exception as e:
        logger.error("Failed to start group game: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start group game: {str(e)}")


@router.post("/join", response_model=GroupGameInfo)
async def join_group_game(
    request: JoinGroupGameRequest,
    http_request: Request,
    user: User = Depends(get_user_from_request),
    redis=Depends(get_redis_client),
) -> GroupGameInfo:
    """
    Join an existing group game.

    This is called when a user taps the "Tap to Sit" button in the group.
    """
    try:
        game_id = request.game_id

        # Get game metadata
        meta_key = f"{GROUP_GAME_META_PREFIX}{game_id}"
        meta_data = await redis.get(meta_key)
        if not meta_data:
            raise HTTPException(status_code=404, detail="Game not found")

        game_meta = json.loads(meta_data)

        # Get current players
        players_key = f"{GROUP_GAME_PLAYERS_PREFIX}{game_id}"
        players_data = await redis.get(players_key)
        players = json.loads(players_data) if players_data else []

        # Check if already joined
        if any(p["id"] == user.id for p in players):
            return GroupGameInfo(
                game_id=game_id,
                chat_id=game_meta["chat_id"],
                initiator_id=game_meta["initiator_id"],
                initiator_name=game_meta["initiator_name"],
                players=players,
                message_id=game_meta.get("message_id"),
                status=game_meta["status"],
                created_at=game_meta["created_at"],
                min_players=game_meta.get("min_players", 2),
            )

        # Add player
        players.append(
            {
                "id": user.id,
                "name": request.user_name or user.username or f"Player{user.id}",
                "joined_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Update Redis
        await redis.setex(players_key, 3600, json.dumps(players))

        # Update group message
        bot_service = get_bot_service()
        if game_meta.get("message_id"):
            miniapp_url = os.getenv("MINIAPP_URL", "https://your-miniapp-url.com")
            await bot_service.update_group_game_message(
                chat_id=game_meta["chat_id"],
                message_id=game_meta["message_id"],
                players=players,
                game_id=game_id,
                min_players=game_meta.get("min_players", 2),
                miniapp_url=miniapp_url,
            )

        # Check if we can auto-start (enough players)
        min_players = game_meta.get("min_players", 2)
        if len(players) >= min_players and game_meta["status"] == "waiting":
            # Mark as starting - actual game start will be handled by bot
            game_meta["status"] = "starting"
            await redis.setex(meta_key, 3600, json.dumps(game_meta))

        return GroupGameInfo(
            game_id=game_id,
            chat_id=game_meta["chat_id"],
            initiator_id=game_meta["initiator_id"],
            initiator_name=game_meta["initiator_name"],
            players=players,
            message_id=game_meta.get("message_id"),
            status=game_meta["status"],
            created_at=game_meta["created_at"],
            min_players=min_players,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to join group game: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to join game: {str(e)}")


@router.get("/{game_id}", response_model=GroupGameInfo)
async def get_group_game(
    game_id: str,
    http_request: Request,
    user: User = Depends(get_user_from_request),
    redis=Depends(get_redis_client),
) -> GroupGameInfo:
    """Get current status of a group game."""
    try:
        # Get game metadata
        meta_key = f"{GROUP_GAME_META_PREFIX}{game_id}"
        meta_data = await redis.get(meta_key)
        if not meta_data:
            raise HTTPException(status_code=404, detail="Game not found")

        game_meta = json.loads(meta_data)

        # Get players
        players_key = f"{GROUP_GAME_PLAYERS_PREFIX}{game_id}"
        players_data = await redis.get(players_key)
        players = json.loads(players_data) if players_data else []

        return GroupGameInfo(
            game_id=game_id,
            chat_id=game_meta["chat_id"],
            initiator_id=game_meta["initiator_id"],
            initiator_name=game_meta["initiator_name"],
            players=players,
            message_id=game_meta.get("message_id"),
            status=game_meta["status"],
            created_at=game_meta["created_at"],
            min_players=game_meta.get("min_players", 2),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get group game: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get game: {str(e)}")


@router.get("/chats/list", response_model=List[Dict[str, Any]])
async def list_user_chats(
    http_request: Request,
    user: User = Depends(get_user_from_request),
) -> List[Dict[str, Any]]:
    """
    Get list of groups/chats available for group games.

    Note: Telegram Bot API limitations mean we can't directly list all groups.
    This endpoint returns an empty list by default, but could be enhanced with:
    - A database of known groups
    - Manual configuration
    - Tracking when bot is added to groups
    """
    try:
        bot_service = get_bot_service()
        chats = await bot_service.get_user_chats(user.id)
        return chats

    except Exception as e:
        logger.error("Failed to list user chats: %s", e, exc_info=True)
        # Return empty list on error rather than failing
        return []


@router.post("/{game_id}/send-miniapp")
async def send_miniapp_to_group(
    game_id: str,
    chat_id: int,
    miniapp_url: Optional[str] = None,
    http_request: Request = ...,
    user: User = Depends(get_user_from_request),
) -> Dict[str, Any]:
    """
    Send a mini-app button message to a group.

    This allows the mini-app to send a message with a mini-app button to a group.
    """
    try:
        bot_service = get_bot_service()
        url = miniapp_url or os.getenv("MINIAPP_URL", "https://your-miniapp-url.com")
        message_id = await bot_service.send_miniapp_button_to_group(
            chat_id=chat_id,
            miniapp_url=url,
            text="🎮 Who wants to join? ✅ Tap to sit.",
        )

        if message_id:
            return {"success": True, "message_id": message_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")

    except Exception as e:
        logger.error("Failed to send mini-app to group: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


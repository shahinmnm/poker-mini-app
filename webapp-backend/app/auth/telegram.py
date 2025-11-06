"""Telegram WebApp authentication helpers."""

from __future__ import annotations

import base64
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Query, Request


class TelegramAuthError(HTTPException):
    """HTTP 401 error raised when Telegram authentication fails."""

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(status_code=401, detail=detail)


@dataclass
class UserContext:
    """Minimal user representation extracted from Telegram initData."""

    id: int
    username: Optional[str]
    lang: Optional[str]


def _get_bot_token() -> str:
    """Return the Telegram bot token from environment variables."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    # Backwards compatibility with older env names
    legacy = os.getenv("POKERBOT_TOKEN") or os.getenv("BOT_TOKEN")
    return legacy or ""


def _get_jwt_secret() -> str:
    secret = os.getenv("TELEGRAM_JWT_SECRET")
    if secret:
        return secret
    # Fall back to bot token so deployments without a dedicated secret still work.
    return _get_bot_token()


def _get_max_age_seconds() -> int:
    raw = os.getenv("TELEGRAM_INITDATA_MAX_AGE", os.getenv("POKER_INITDATA_MAX_AGE", "600"))
    try:
        value = int(raw)
        return max(value, 0)
    except ValueError:
        return 600


def _get_jwt_ttl_seconds() -> int:
    raw = os.getenv("TELEGRAM_JWT_TTL", "900")
    try:
        value = int(raw)
        return max(value, 60)
    except ValueError:
        return 900


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _derive_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), digestmod="sha256").digest()


def _build_data_check_string(pairs: Dict[str, str]) -> str:
    items = [(k, v) for k, v in pairs.items() if k != "hash"]
    items.sort(key=lambda item: item[0])
    return "\n".join(f"{k}={v}" for k, v in items)


def _parse_init_data_raw(init_data: str) -> Dict[str, str]:
    try:
        return dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except Exception as exc:  # pragma: no cover - defensive
        raise TelegramAuthError("Invalid initData format") from exc


def validate_init_data(
    init_data: str,
    *,
    bot_token: Optional[str] = None,
    max_age_seconds: Optional[int] = None,
) -> Tuple[Dict[str, str], UserContext]:
    """Validate Telegram initData and return both parsed pairs and user context."""

    token = bot_token or _get_bot_token()
    if not token:
        raise HTTPException(status_code=500, detail="Telegram bot token is not configured")

    parsed = _parse_init_data_raw(init_data)
    init_hash = parsed.get("hash")
    if not init_hash:
        raise TelegramAuthError("Missing initData hash")

    secret = _derive_secret_key(token)
    expected_hash = hmac.new(secret, _build_data_check_string(parsed).encode("utf-8"), digestmod="sha256").hexdigest()

    if not hmac.compare_digest(init_hash, expected_hash):
        raise TelegramAuthError("Bad initData signature")

    if max_age_seconds is None:
        max_age_seconds = _get_max_age_seconds()
    if max_age_seconds:
        try:
            auth_date = int(parsed.get("auth_date", "0"))
        except ValueError:
            auth_date = 0
        if auth_date:
            now = int(datetime.now(timezone.utc).timestamp())
            if now - auth_date > max_age_seconds:
                raise TelegramAuthError("initData expired")

    user_json = parsed.get("user")
    if not user_json:
        raise TelegramAuthError("Missing user in initData")

    try:
        user_payload = json.loads(user_json)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Malformed user payload") from exc

    user_id = user_payload.get("id")
    if user_id is None:
        raise TelegramAuthError("Missing user.id in initData")

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise TelegramAuthError("Invalid user.id in initData")

    username = user_payload.get("username")
    lang = user_payload.get("language_code") or user_payload.get("lang")

    return parsed, UserContext(id=user_id_int, username=username, lang=lang)


def create_user_jwt(user: UserContext, *, secret: Optional[str] = None, ttl_seconds: Optional[int] = None) -> str:
    key = secret or _get_jwt_secret()
    if not key:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")

    ttl = ttl_seconds or _get_jwt_ttl_seconds()
    issued_at = int(time.time())
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "lang": user.lang,
        "iat": issued_at,
        "exp": issued_at + ttl,
    }
    header = {"alg": "HS256", "typ": "JWT"}

    signing_input = f"{_base64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_base64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(key.encode("utf-8"), signing_input.encode("utf-8"), digestmod="sha256").digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def decode_user_jwt(token: str, *, secret: Optional[str] = None) -> UserContext:
    key = secret or _get_jwt_secret()
    if not key:
        raise TelegramAuthError("JWT secret missing")

    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
    except ValueError as exc:
        raise TelegramAuthError("Invalid token format") from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected_signature = hmac.new(key.encode("utf-8"), signing_input.encode("utf-8"), digestmod="sha256").digest()

    try:
        provided_signature = _base64url_decode(signature_b64)
    except Exception as exc:  # pragma: no cover - defensive
        raise TelegramAuthError("Malformed token signature") from exc

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise TelegramAuthError("Bad token signature")

    try:
        payload = json.loads(_base64url_decode(payload_b64))
    except Exception as exc:  # pragma: no cover - defensive
        raise TelegramAuthError("Malformed token payload") from exc

    exp = payload.get("exp")
    if isinstance(exp, int) and exp < int(time.time()):
        raise TelegramAuthError("Token expired")

    sub = payload.get("sub")
    if sub is None:
        raise TelegramAuthError("Token subject missing")

    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise TelegramAuthError("Invalid token subject") from exc

    return UserContext(id=user_id, username=payload.get("username"), lang=payload.get("lang"))


async def require_telegram_user(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-Init-Data"),
    init_data_query: Optional[str] = Query(default=None, alias="initData"),
    authorization: Optional[str] = Header(default=None),
) -> UserContext:
    """FastAPI dependency that enforces Telegram WebApp authentication."""

    raw_authorization = (authorization or "").strip()
    if raw_authorization.lower().startswith("bearer "):
        bearer_value = raw_authorization.split(" ", 1)[1].strip()
        if "." in bearer_value:
            return decode_user_jwt(bearer_value)
        # Backwards compatibility: treat Bearer initData as raw initData
        _, user = validate_init_data(bearer_value)
        return user

    init_data = x_telegram_init_data or init_data_query or request.query_params.get("initData")
    if not init_data:
        raise TelegramAuthError("Telegram initData missing")

    _, user = validate_init_data(init_data)
    return user

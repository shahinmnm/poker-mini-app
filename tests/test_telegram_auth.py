import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEBAPP_BACKEND = PROJECT_ROOT / "webapp-backend"
if str(WEBAPP_BACKEND) not in sys.path:
    sys.path.insert(0, str(WEBAPP_BACKEND))

from app.auth import TelegramAuthError, UserContext, decode_user_jwt, create_user_jwt, validate_init_data


def _build_init_data(bot_token: str, *, user_id: int = 12345, username: str = "alice", lang: str = "en") -> str:
    payload = {
        "query_id": "AAEAAAE",  # arbitrary stable value
        "user": json.dumps({"id": user_id, "username": username, "language_code": lang}, separators=(",", ":")),
        "auth_date": str(int(time.time())),
    }
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    dcs = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    payload["hash"] = hmac.new(secret, dcs.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(payload)


def test_validate_init_data_accepts_signed_payload():
    bot_token = "123456:ABCDEF"
    init_data = _build_init_data(bot_token, user_id=777, username="pokerpro", lang="fr")

    parsed, user = validate_init_data(init_data, bot_token=bot_token, max_age_seconds=600)

    assert parsed["query_id"] == "AAEAAAE"
    assert isinstance(user, UserContext)
    assert user.id == 777
    assert user.username == "pokerpro"
    assert user.lang == "fr"


def test_validate_init_data_rejects_bad_signature():
    bot_token = "123456:ABCDEF"
    init_data = _build_init_data(bot_token)
    tampered = init_data.replace("alice", "mallory")

    with pytest.raises(TelegramAuthError):
        validate_init_data(tampered, bot_token=bot_token, max_age_seconds=600)


def test_user_jwt_roundtrip():
    user = UserContext(id=42, username="dealer", lang="en")
    token = create_user_jwt(user, secret="secret-key", ttl_seconds=120)
    decoded = decode_user_jwt(token, secret="secret-key")

    assert decoded.id == user.id
    assert decoded.username == user.username
    assert decoded.lang == user.lang

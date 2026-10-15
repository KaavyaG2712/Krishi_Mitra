"""Short-lived, signed capabilities; no farmer identity or coordinates in logs."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException
from app.core.config import get_settings

_development_key = secrets.token_bytes(32)


def _key() -> bytes:
    settings = get_settings()
    if settings.signing_secret:
        return settings.signing_secret.encode()
    if settings.environment != "development":
        raise RuntimeError("SIGNING_SECRET is required outside development")
    return _development_key


def sign(value: dict, purpose: str) -> str:
    data = json.dumps({"value": value, "purpose": purpose, "expires": int(time.time()) + 86400}, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(data).decode()
    return encoded + "." + hmac.new(_key(), encoded.encode(), hashlib.sha256).hexdigest()


def verify(token: str, purpose: str) -> dict:
    try:
        encoded, signature = token.split(".")
        if not hmac.compare_digest(signature, hmac.new(_key(), encoded.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(encoded))
        if data["purpose"] != purpose or data["expires"] < time.time():
            raise ValueError()
        return data["value"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, "This session has expired. Start a new conversation or submit the soil values again.") from None

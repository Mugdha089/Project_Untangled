"""Local demo authentication helpers (stdlib-only signed bearer tokens)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import run_storage

TOKEN_TTL_SECONDS = 12 * 60 * 60
bearer_scheme = HTTPBearer(auto_error=False)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_token(user: dict[str, Any]) -> tuple[str, int]:
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    payload = _b64(json.dumps({"sub": user["user_id"], "email": user["email"], "exp": expires}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(run_storage.auth_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", expires


def _decode(token: str) -> dict[str, Any]:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64(hmac.new(run_storage.auth_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if int(data["exp"]) <= int(time.time()):
            raise ValueError("expired")
        return data
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session.", headers={"WWW-Authenticate": "Bearer"}) from None


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    claims = _decode(credentials.credentials)
    user = run_storage.find_user(claims.get("email", ""))
    if user is None or user["user_id"] != claims.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired session.", headers={"WWW-Authenticate": "Bearer"})
    return {"user_id": user["user_id"], "email": user["email"], "full_name": user["full_name"], "role": user["role"]}

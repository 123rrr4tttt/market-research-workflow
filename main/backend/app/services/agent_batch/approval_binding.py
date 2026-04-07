from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from typing import Any


_LOCK = threading.RLock()
_PENDING: dict[str, dict[str, Any]] = {}
_APPROVED: dict[str, dict[str, Any]] = {}

REASON_APPROVAL_REQUIRED = "approval_required"
REASON_APPROVAL_NOT_FOUND = "approval_token_not_found"
REASON_APPROVAL_EXPIRED = "approval_token_expired"
REASON_APPROVAL_BINDING_MISMATCH = "approval_binding_mismatch"
REASON_APPROVAL_NOT_APPROVED = "approval_not_approved"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_binding(binding: dict[str, Any]) -> dict[str, Any]:
    argv = binding.get("argv")
    if isinstance(argv, str):
        argv = [argv]
    argv_out = [str(x or "").strip() for x in (argv or []) if str(x or "").strip()]
    env = binding.get("env")
    env_out: dict[str, str] = {}
    if isinstance(env, dict):
        for k, v in env.items():
            key = str(k or "").strip()
            if key:
                env_out[key] = str(v or "")
    return {
        "argv": argv_out,
        "cwd": str(binding.get("cwd") or "").strip() or None,
        "env": env_out,
        "channel": str(binding.get("channel") or "").strip() or None,
        "project_key": str(binding.get("project_key") or "").strip() or None,
    }


def hash_binding(binding: dict[str, Any]) -> str:
    normalized = _normalize_binding(binding)
    return hashlib.sha256(_stable_json(normalized).encode("utf-8")).hexdigest()


def request_approval(*, binding: dict[str, Any], ttl_seconds: int = 600) -> dict[str, Any]:
    now = int(time.time())
    token = secrets.token_urlsafe(24)
    payload = {
        "token": token,
        "binding_hash": hash_binding(binding),
        "binding": _normalize_binding(binding),
        "created_at": now,
        "expires_at": now + max(60, int(ttl_seconds)),
        "approved": False,
        "approved_at": None,
    }
    with _LOCK:
        _PENDING[token] = payload
    return {
        "approval_token": token,
        "binding_hash": payload["binding_hash"],
        "created_at": payload["created_at"],
        "expires_at": payload["expires_at"],
    }


def approve_approval(*, approval_token: str) -> dict[str, Any]:
    token = str(approval_token or "").strip()
    if not token:
        raise ValueError("approval_token is required")
    now = int(time.time())
    with _LOCK:
        payload = _PENDING.get(token)
        if not payload:
            payload = _APPROVED.get(token)
        if not payload:
            raise KeyError(REASON_APPROVAL_NOT_FOUND)
        if int(payload.get("expires_at") or 0) < now:
            raise ValueError(REASON_APPROVAL_EXPIRED)
        payload["approved"] = True
        payload["approved_at"] = now
        _APPROVED[token] = payload
        _PENDING.pop(token, None)
    return {
        "approval_token": token,
        "approved": True,
        "approved_at": now,
        "expires_at": int(payload.get("expires_at") or 0),
    }


def verify_approval_token(*, approval_token: str | None, binding: dict[str, Any]) -> tuple[bool, str | None]:
    token = str(approval_token or "").strip()
    if not token:
        return False, REASON_APPROVAL_REQUIRED
    now = int(time.time())
    with _LOCK:
        payload = _APPROVED.get(token) or _PENDING.get(token)
    if not payload:
        return False, REASON_APPROVAL_NOT_FOUND
    if int(payload.get("expires_at") or 0) < now:
        return False, REASON_APPROVAL_EXPIRED
    if not bool(payload.get("approved")):
        return False, REASON_APPROVAL_NOT_APPROVED
    expected = str(payload.get("binding_hash") or "")
    actual = hash_binding(binding)
    if expected != actual:
        return False, REASON_APPROVAL_BINDING_MISMATCH
    return True, None


def cleanup_expired() -> None:
    now = int(time.time())
    with _LOCK:
        for store in (_PENDING, _APPROVED):
            expired = [k for k, v in store.items() if int(v.get("expires_at") or 0) < now]
            for key in expired:
                store.pop(key, None)


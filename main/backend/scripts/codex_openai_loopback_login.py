#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event
from urllib.parse import parse_qs, urlencode, urlparse

import httpx


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _save_token_sink(path: Path, profile: str, payload: dict) -> None:
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
    profiles = existing.get("profiles") if isinstance(existing.get("profiles"), dict) else {}
    profiles[profile] = payload
    final = {
        "schema_version": "codex_oauth_sink.v1",
        "active_profile": profile,
        "profiles": profiles,
        "updated_at": int(time.time()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw-style OpenAI OAuth loopback login")
    parser.add_argument("--authorize-url", default="https://auth.openai.com/oauth/authorize")
    parser.add_argument("--token-url", default="https://auth.openai.com/oauth/token")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--scope", default="openid profile email offline_access")
    parser.add_argument("--redirect-uri", default="http://127.0.0.1:1455/auth/callback")
    parser.add_argument("--sink-path", default="~/.codex/auth_openai.json")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    challenge = _pkce_s256(verifier)

    callback_done = Event()
    callback_data: dict[str, str] = {}

    parsed = urlparse(args.redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 1455)
    callback_path = parsed.path or "/auth/callback"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args):
            return

        def do_GET(self):
            parsed_req = urlparse(self.path)
            if parsed_req.path != callback_path:
                self.send_response(404)
                self.end_headers()
                return
            query = parse_qs(parsed_req.query)
            callback_data["code"] = (query.get("code") or [""])[0]
            callback_data["state"] = (query.get("state") or [""])[0]
            callback_data["error"] = (query.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h3>Codex auth success</h3><p>You can close this window.</p></body></html>"
            )
            callback_done.set()

    server = HTTPServer((host, port), Handler)

    authorize_query = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "scope": args.scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{args.authorize_url}?{urlencode(authorize_query)}"

    print(f"[codex-oauth] listening callback at {args.redirect_uri}")
    print(f"[codex-oauth] opening browser: {authorize_url}")
    webbrowser.open(authorize_url)

    server.timeout = 1
    start = time.time()
    while time.time() - start < max(30, args.timeout):
        server.handle_request()
        if callback_done.is_set():
            break
    server.server_close()

    if not callback_done.is_set():
        print("[codex-oauth] timeout waiting callback", file=sys.stderr)
        return 2

    if callback_data.get("error"):
        print(f"[codex-oauth] oauth error: {callback_data['error']}", file=sys.stderr)
        return 2
    code = str(callback_data.get("code") or "").strip()
    recv_state = str(callback_data.get("state") or "").strip()
    if not code or recv_state != state:
        print("[codex-oauth] invalid callback state/code", file=sys.stderr)
        return 2

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": args.redirect_uri,
        "client_id": args.client_id,
        "code_verifier": verifier,
    }
    if args.client_secret.strip():
        token_payload["client_secret"] = args.client_secret.strip()

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            args.token_url,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code >= 400:
        print(f"[codex-oauth] token exchange failed: {resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return 2

    data = resp.json() if resp.content else {}
    now = int(time.time())
    expires_in = int(data.get("expires_in") or 3600)
    sink_payload = {
        "provider": "openai",
        "access_token": str(data.get("access_token") or "").strip() or None,
        "refresh_token": str(data.get("refresh_token") or "").strip() or None,
        "token_type": str(data.get("token_type") or "").strip() or None,
        "scope": str(data.get("scope") or args.scope).strip() or None,
        "expires_at": now + max(300, min(expires_in, 86400 * 7)),
        "created_at": now,
        "id_token": str(data.get("id_token") or "").strip() or None,
    }

    sink_path = Path(args.sink_path).expanduser().resolve()
    _save_token_sink(sink_path, args.profile, sink_payload)
    print(f"[codex-oauth] login success, token sink saved to {sink_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

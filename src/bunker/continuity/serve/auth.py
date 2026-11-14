from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse

_LOGIN_WINDOW_SEC = 300
_MAX_ATTEMPTS = 10
_SESSION_TTL_SEC = 12 * 3600


def _hash_password(password: str, *, salt: bytes) -> str:
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    digest = kdf.derive(password.encode("utf-8"))
    return json.dumps(
        {
            "salt": salt.hex(),
            "digest": digest.hex(),
            "n": 2**15,
            "r": 8,
            "p": 1,
        }
    )


def verify_password(password: str, stored: str) -> bool:
    doc = json.loads(stored)
    salt = bytes.fromhex(doc["salt"])
    expected = bytes.fromhex(doc["digest"])
    kdf = Scrypt(salt=salt, length=32, n=int(doc["n"]), r=int(doc["r"]), p=int(doc["p"]))
    got = kdf.derive(password.encode("utf-8"))
    return hmac.compare_digest(got, expected)


def save_password_hash(auth_path: Path, password: str) -> None:
    salt = secrets.token_bytes(16)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(_hash_password(password, salt=salt), encoding="utf-8")
    try:
        os.chmod(auth_path, 0o600)
    except OSError:
        pass


def auth_configured(auth_path: Path) -> bool:
    return auth_path.is_file() and bool(auth_path.read_text(encoding="utf-8").strip())


@dataclass
class ServeAuthConfig:
    auth_path: Path
    session_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    secure_cookie: bool = False
    _sessions: dict[str, float] = field(default_factory=dict)
    _attempts: dict[str, tuple[int, float]] = field(default_factory=dict)

    def _sign_session(self, sid: str, exp: float) -> str:
        payload = f"{sid}.{int(exp)}".encode()
        sig = hmac.new(self.session_secret, payload, hashlib.sha256).hexdigest()
        return f"{sid}.{int(exp)}.{sig}"

    def _verify_session(self, token: str) -> bool:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        sid, exp_s, sig = parts
        try:
            exp = float(exp_s)
        except ValueError:
            return False
        if exp < time.time():
            return False
        expected = hmac.new(
            self.session_secret,
            f"{sid}.{int(exp)}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return sid in self._sessions

    def issue_session(self, response: Response) -> None:
        sid = secrets.token_urlsafe(24)
        exp = time.time() + _SESSION_TTL_SEC
        self._sessions[sid] = exp
        token = self._sign_session(sid, exp)
        response.set_cookie(
            "bunker_session",
            token,
            httponly=True,
            samesite="strict",
            secure=self.secure_cookie,
            max_age=_SESSION_TTL_SEC,
        )

    def check_login_allowed(self, client_ip: str) -> bool:
        now = time.time()
        count, start = self._attempts.get(client_ip, (0, now))
        if now - start > _LOGIN_WINDOW_SEC:
            count = 0
            start = now
        return count < _MAX_ATTEMPTS

    def record_failed_login(self, client_ip: str) -> None:
        now = time.time()
        count, start = self._attempts.get(client_ip, (0, now))
        if now - start > _LOGIN_WINDOW_SEC:
            count, start = 0, now
        self._attempts[client_ip] = (count + 1, start)

    def verify_login(self, password: str) -> bool:
        if not self.auth_path.is_file():
            return False
        stored = self.auth_path.read_text(encoding="utf-8")
        return verify_password(password, stored)


def loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def serve_auth_middleware(auth: ServeAuthConfig, bind_host: str):  # type: ignore[no-untyped-def]
    require = not loopback_host(bind_host)

    async def middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        if not require:
            return await call_next(request)
        if request.url.path in ("/login", "/healthz"):
            return await call_next(request)
        token = request.cookies.get("bunker_session", "")
        if token and auth._verify_session(token):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return HTMLResponse(
            "<h1>401 Unauthorized</h1><p>POST /login with password to obtain a session.</p>",
            status_code=401,
        )

    return middleware
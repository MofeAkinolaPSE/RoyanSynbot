from __future__ import annotations

import time
import logging
from functools import partial
from typing import Dict, Optional
from fastapi import Request, HTTPException, Query
import jwt
from jwt import PyJWKClient
from .constants import JWT_SECRET, RATE_LIMIT, JWT_AUDIENCE, AUTH0_DOMAIN, AUTH0_AUDIENCE, AUTH0_ISSUER
from starlette.middleware.base import BaseHTTPMiddleware



_rate_store: Dict[str, list] = {}
_jwks_client: PyJWKClient | None = None


def _get_auth0_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if not AUTH0_DOMAIN:
        return None
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
    return _jwks_client


def decode_jwt_token(token: str, required_role: str | None = None) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg not in ("HS256", "RS256"):
            raise HTTPException(status_code=401, detail="Unsupported token algorithm")
        options = {"require": ["exp", "iat"], "verify_exp": True}
        leeway = 30
        if alg == "RS256" and AUTH0_DOMAIN and AUTH0_AUDIENCE:
            jwks_client = _get_auth0_jwks_client()
            if jwks_client is None:
                raise HTTPException(status_code=401, detail="Auth0 not configured")
            signing_key = jwks_client.get_signing_key_from_jwt(token).key
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                options=options,
                audience=AUTH0_AUDIENCE,
                issuer=AUTH0_ISSUER or None,
                leeway=leeway,
            )
        else:
            audience = JWT_AUDIENCE or None
            if audience:
                payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options=options, audience=audience, leeway=leeway)
            else:
                payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options=options, leeway=leeway)
    except jwt.ExpiredSignatureError:
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            logging.warning(f"JWT Expired: exp={unverified.get('exp')}, now={time.time()}")
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        logging.warning(f"JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    if required_role:
        allowed = (required_role,) if isinstance(required_role, str) else required_role
        user_roles = payload.get("roles") or payload.get("permissions") or []
        # admin is a superrole — bypasses all role checks
        if "admin" not in user_roles and not any(r in user_roles for r in allowed):
            raise HTTPException(status_code=403, detail="Insufficient role")
    return payload


def verify_jwt(request: Request, required_role: Optional[str] = Query(None, include_in_schema=False)) -> dict:
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    payload = decode_jwt_token(token, required_role=required_role)
    try:
        request.state.user = payload
    except Exception:
        pass
    return payload


def require_role(*roles: str):
    """Return a FastAPI dependency that verifies JWT and enforces at least one of *roles*.

    Accepts one or more role strings: require_role("admin") or require_role("admin", "finance").
    Uses a closure so FastAPI can correctly introspect the Request parameter.
    """
    async def _dep(request: Request) -> dict:
        return verify_jwt(request, required_role=roles)
    return _dep



def rate_limit(request: Request, key: str | None = None, limit: int | None = None) -> None:
    """In-memory per-minute rate limiting.

    Bucket key priority:
      1. Caller-supplied key
      2. Authenticated user sub extracted from Bearer token (per-user enforcement)
      3. Client IP address as fallback (unauthenticated / widget traffic)

    For MVP only — replace with Redis for multi-replica deployments.
    """
    limit = limit or RATE_LIMIT
    now = int(time.time())
    minute = now // 60

    if key is None:
        _auth = request.headers.get("Authorization", "")
        if _auth.lower().startswith("bearer "):
            try:
                _payload = jwt.decode(
                    _auth[7:],
                    JWT_SECRET,
                    algorithms=["HS256"],
                    options={"verify_exp": False, "verify_signature": True},
                )
                _uid = _payload.get("sub") or _payload.get("id")
                if _uid:
                    key = f"user:{_uid}"
            except Exception:
                pass
        if key is None:
            key = request.client.host if request.client else "unknown"

    bucket_key = f"{key}:{minute}"
    bucket = _rate_store.setdefault(bucket_key, [])
    bucket.append(now)
    # prune buckets older than 2 minutes
    for old_key in list(_rate_store.keys()):
        if old_key.endswith(str(minute - 2)):
            _rate_store.pop(old_key, None)
    if len(bucket) > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            return response
        finally:
            dur_ms = (time.perf_counter() - start) * 1000
            path = request.url.path
            method = request.method
            logging.info(f"{method} {path} handled in {dur_ms:.1f} ms")

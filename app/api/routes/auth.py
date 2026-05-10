"""Authentication routes and dependencies — Clerk JWT verification."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)
settings = get_settings()

_CLERK_JWKS_URL = "https://api.clerk.com/v1/jwks"
_jwks_cache: dict[str, dict] = {}


async def _fetch_jwks() -> dict[str, dict]:
    headers = {}
    if settings.clerk_secret_key:
        headers["Authorization"] = f"Bearer {settings.clerk_secret_key}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_CLERK_JWKS_URL, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return {k["kid"]: k for k in data.get("keys", [])}


async def _get_jwks() -> dict[str, dict]:
    global _jwks_cache
    if not _jwks_cache:
        _jwks_cache = await _fetch_jwks()
    return _jwks_cache


async def _verify_clerk_token(token: str) -> dict:
    """Verify a Clerk-issued JWT and return its claims."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Malformed token") from exc

    kid = header.get("kid", "")
    keys = await _get_jwks()

    if kid not in keys:
        global _jwks_cache
        _jwks_cache = {}
        keys = await _get_jwks()

    if kid not in keys:
        raise HTTPException(status_code=401, detail="Unknown signing key")

    try:
        return jwt.decode(
            token,
            keys[kid],
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {exc}") from exc


@router.get("/verify")
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Verify a Clerk JWT and return the user ID."""
    if not credentials:
        raise HTTPException(status_code=401, detail="No token provided")
    claims = await _verify_clerk_token(credentials.credentials)
    return {"valid": True, "user_id": claims.get("sub")}


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Dependency that enforces Clerk auth. Returns the Clerk user_id."""
    if settings.auth_disabled:
        return "dev-user"

    if not settings.clerk_secret_key:
        raise HTTPException(
            status_code=500,
            detail="Auth not configured. Set CLERK_SECRET_KEY environment variable.",
        )

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    claims = await _verify_clerk_token(credentials.credentials)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user identity")
    return user_id

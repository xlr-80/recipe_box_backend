import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InvalidTokenError(Exception):
    pass


# ---------- passwords ----------

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ---------- access tokens (stateless JWT, short-lived) ----------

def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user id (subject) if the access token is valid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Could not validate token") from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Expected an access token")

    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError("Token missing subject")
    return subject


# ---------- refresh tokens (opaque, DB-backed, revocable) ----------
#
# Unlike the access token, the refresh token is NOT a JWT. It's a random
# opaque string handed to the client; only its SHA-256 hash is stored in
# Mongo (in the `refresh_tokens` collection). This means:
#   - a stolen database dump doesn't hand out usable refresh tokens
#   - a token can be revoked server-side (logout, rotation, abuse)
#   - "is this still valid" is a real DB check, not just a signature check

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

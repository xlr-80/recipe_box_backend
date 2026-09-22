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


# ---------- opaque, hashed, DB-backed tokens ----------
# Shared pattern for both refresh tokens and email-verification tokens:
# a random opaque string is handed out once (in the response, or in the
# verification email); only its SHA-256 hash is ever stored. Neither
# type is a JWT — there's nothing to "decode," only to look up.

def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def email_verification_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)

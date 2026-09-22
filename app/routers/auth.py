import asyncio
from datetime import datetime, timezone

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .. import models, schemas
from ..config import settings
from ..dependencies import get_current_user
from ..email_service import send_verification_email
from ..serializers import generate_unique_username, user_out
from ..security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    refresh_token_expiry,
    email_verification_expiry,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_token_pair(user_id: str) -> schemas.TokenPair:
    access = create_access_token(user_id)
    raw_refresh = generate_opaque_token()
    await models.RefreshToken(
        user_id=user_id,
        token_hash=hash_opaque_token(raw_refresh),
        expires_at=refresh_token_expiry(),
    ).insert()
    return schemas.TokenPair(access_token=access, refresh_token=raw_refresh)


async def _send_verification_email(user: models.User) -> None:
    raw_token = generate_opaque_token()
    await models.EmailVerificationToken(
        user_id=str(user.id),
        token_hash=hash_opaque_token(raw_token),
        expires_at=email_verification_expiry(),
    ).insert()
    # smtplib is blocking — never call it directly inside an async route,
    # push it to a thread so it doesn't stall the event loop.
    await asyncio.to_thread(send_verification_email, user.email, user.full_name, raw_token)


@router.post("/register", response_model=schemas.TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: schemas.UserCreate):
    existing = await models.User.find_one(models.User.email == payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    user = models.User(
        full_name=payload.full_name,
        username=await generate_unique_username(payload.full_name),
        email=payload.email,
        hashed_password=hash_password(payload.password),
        auth_provider=models.AuthProvider.password,
        is_email_verified=False,
    )
    await user.insert()
    await _send_verification_email(user)

    return await _issue_token_pair(str(user.id))


@router.post("/login", response_model=schemas.TokenPair)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """`username` should be the user's email."""
    user = await models.User.find_one(models.User.email == form_data.username)
    if user is None or user.hashed_password is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in")

    return await _issue_token_pair(str(user.id))


@router.post("/google", response_model=schemas.TokenPair)
async def google_auth(payload: schemas.GoogleAuthRequest):
    """Verifies a Google ID token (sent by the client after Google
    Sign-In) and either logs in the matching existing account or
    creates a new one. Either way, our own JWT/refresh token pair is
    returned — the client never uses the Google token again after this
    call."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google sign-in is not configured on this server")

    try:
        # verify_oauth2_token checks the signature, expiry, issuer, AND
        # that `aud` matches our client ID — rejecting a token minted
        # for a different app.
        claims = await asyncio.to_thread(
            google_id_token.verify_oauth2_token,
            payload.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {exc}")

    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token did not include an email")
    if not claims.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account email is not verified")

    full_name = claims.get("name") or email.split("@")[0]
    avatar_url = claims.get("picture")

    user = await models.User.find_one(models.User.email == email)
    if user is None:
        # New account via Google — no password, pre-verified since
        # Google already confirmed the email address.
        user = models.User(
            full_name=full_name,
            username=await generate_unique_username(full_name),
            email=email,
            hashed_password=None,
            auth_provider=models.AuthProvider.google,
            is_email_verified=True,
            avatar_url=avatar_url,
        )
        await user.insert()
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    # Existing account, whether it was originally created via password
    # or Google — either way, a verified Google login for a matching
    # email is enough to sign in.

    return await _issue_token_pair(str(user.id))


@router.post("/refresh", response_model=schemas.TokenPair)
async def refresh(payload: schemas.RefreshRequest):
    token_hash = hash_opaque_token(payload.refresh_token)
    record = await models.RefreshToken.find_one(
        models.RefreshToken.token_hash == token_hash,
        models.RefreshToken.revoked == False,  # noqa: E712
    )
    if record is None or record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user = await models.User.get(PydanticObjectId(record.user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    record.revoked = True
    await record.save()

    return await _issue_token_pair(record.user_id)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(payload: schemas.RefreshRequest):
    token_hash = hash_opaque_token(payload.refresh_token)
    record = await models.RefreshToken.find_one(models.RefreshToken.token_hash == token_hash)
    if record and not record.revoked:
        record.revoked = True
        await record.save()
    return {"message": "Logged out"}


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(current_user: models.User = Depends(get_current_user)):
    if current_user.is_email_verified:
        return {"message": "Email is already verified"}
    await _send_verification_email(current_user)
    return {"message": "Verification email sent"}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(payload: schemas.VerifyEmailRequest):
    token_hash = hash_opaque_token(payload.token)
    record = await models.EmailVerificationToken.find_one(
        models.EmailVerificationToken.token_hash == token_hash,
        models.EmailVerificationToken.used == False,  # noqa: E712
    )
    if record is None or record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link")

    user = await models.User.get(PydanticObjectId(record.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_email_verified = True
    await user.save()
    record.used = True
    await record.save()

    return {"message": "Email verified"}


@router.get("/me", response_model=schemas.UserOut)
async def read_current_user(current_user: models.User = Depends(get_current_user)):
    return user_out(current_user)

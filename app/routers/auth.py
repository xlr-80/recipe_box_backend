from datetime import datetime, timezone

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from .. import models, schemas
from ..dependencies import get_current_user
from ..serializers import generate_unique_username, user_out
from ..security import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_token_pair(user_id: str) -> schemas.TokenPair:
    access = create_access_token(user_id)
    raw_refresh = generate_refresh_token()
    await models.RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=refresh_token_expiry(),
    ).insert()
    return schemas.TokenPair(access_token=access, refresh_token=raw_refresh)


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
    )
    await user.insert()

    return await _issue_token_pair(str(user.id))


@router.post("/login", response_model=schemas.TokenPair)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Uses OAuth2PasswordRequestForm (username + password fields) so this
    endpoint also works with the interactive /docs 'Authorize' button.
    `username` should be the user's email."""
    user = await models.User.find_one(models.User.email == form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return await _issue_token_pair(str(user.id))


@router.post("/refresh", response_model=schemas.TokenPair)
async def refresh(payload: schemas.RefreshRequest):
    """Looks the refresh token up by its hash in Mongo (never by the raw
    value), checks it hasn't been revoked or expired, then rotates it:
    the old one is marked revoked and a brand new access/refresh pair is
    issued. If someone replays an old, already-rotated refresh token,
    this will reject it — that's a signal the token may have leaked."""
    token_hash = hash_refresh_token(payload.refresh_token)
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
    """Revokes a refresh token so it can no longer be used, effectively
    logging that device/session out. Always returns success (even if the
    token was already invalid) to avoid leaking whether a token exists."""
    token_hash = hash_refresh_token(payload.refresh_token)
    record = await models.RefreshToken.find_one(models.RefreshToken.token_hash == token_hash)
    if record and not record.revoked:
        record.revoked = True
        await record.save()
    return {"message": "Logged out"}


@router.get("/me", response_model=schemas.UserOut)
async def read_current_user(current_user: models.User = Depends(get_current_user)):
    return user_out(current_user)

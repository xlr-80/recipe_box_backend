from dataclasses import dataclass

from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer

from . import models
from .security import decode_access_token, InvalidTokenError

# tokenUrl only matters for the interactive /docs "Authorize" button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_error

    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise credentials_error

    try:
        oid = PydanticObjectId(user_id)
    except Exception:
        raise credentials_error

    user = await models.User.get(oid)
    if user is None or not user.is_active:
        raise credentials_error
    return user


async def get_current_user_optional(token: str | None = Depends(oauth2_scheme)) -> models.User | None:
    """Same as get_current_user but returns None instead of raising —
    used on public endpoints that adapt their response when a caller
    happens to be authenticated (e.g. marking is_favorite)."""
    if token is None:
        return None
    try:
        user_id = decode_access_token(token)
        oid = PydanticObjectId(user_id)
    except Exception:
        return None
    user = await models.User.get(oid)
    return user if (user and user.is_active) else None


@dataclass
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_params(
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Items per page (max 100)"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)

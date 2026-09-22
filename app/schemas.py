from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar, Optional

from pydantic import BaseModel, EmailStr, Field

from .models import Difficulty, Category, AuthProvider

T = TypeVar("T")


# ---------- Generic pagination ----------

class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


# ---------- Auth ----------

class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(description="The ID token returned by Google Sign-In on the client")


class VerifyEmailRequest(BaseModel):
    token: str


# ---------- Users ----------

class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    email: EmailStr
    auth_provider: AuthProvider
    is_email_verified: bool
    bio: Optional[str] = None
    location: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=120)
    bio: Optional[str] = Field(default=None, max_length=280)
    location: Optional[str] = Field(default=None, max_length=120)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class UserProfile(UserOut):
    recipe_count: int
    follower_count: int
    following_count: int
    is_following: bool = False  # relative to the requesting user, if authenticated


class UserCardOut(BaseModel):
    """Lightweight shape for user lists — search results, followers,
    following."""

    id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    recipe_count: int
    follower_count: int
    is_following: bool = False


# ---------- Device tokens (FCM) ----------

class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="android", pattern="^(android|ios|web)$")


# ---------- Recipes ----------

class RecipeSort(str, Enum):
    newest = "newest"
    popular = "popular"


class RecipeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    image_url: Optional[str] = Field(default=None, max_length=500)
    cook_minutes: int = Field(gt=0, le=1440)
    difficulty: Difficulty
    category: Category
    ingredients: list[str] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)


class RecipeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    image_url: Optional[str] = Field(default=None, max_length=500)
    cook_minutes: Optional[int] = Field(default=None, gt=0, le=1440)
    difficulty: Optional[Difficulty] = None
    category: Optional[Category] = None
    ingredients: Optional[list[str]] = Field(default=None, min_length=1)
    steps: Optional[list[str]] = Field(default=None, min_length=1)


class AuthorOut(BaseModel):
    id: str
    full_name: str
    avatar_url: Optional[str] = None


class RecipeCardOut(BaseModel):
    id: str
    title: str
    image_url: Optional[str] = None
    cook_minutes: int
    difficulty: Difficulty
    category: Category
    rating_avg: float
    rating_count: int
    author: AuthorOut
    is_favorite: bool = False


class RecipeDetailOut(RecipeCardOut):
    ingredients: list[str]
    steps: list[str]
    created_at: datetime


# ---------- Reviews ----------

class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    id: str
    rating: int
    comment: Optional[str] = None
    author: AuthorOut
    created_at: datetime


class RecipeRef(BaseModel):
    """Minimal recipe pointer, used when a review is shown out of the
    context of its recipe's own page (e.g. on a profile's Reviews tab)."""

    id: str
    title: str
    image_url: Optional[str] = None


class ReviewWithRecipeOut(BaseModel):
    """A review shown alongside which recipe it was for — used by
    GET /users/{id}/reviews, since a bare ReviewOut alone doesn't say
    what was reviewed."""

    id: str
    rating: int
    comment: Optional[str] = None
    recipe: RecipeRef
    created_at: datetime

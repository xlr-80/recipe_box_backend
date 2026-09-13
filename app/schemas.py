from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar, Optional

from pydantic import BaseModel, EmailStr, Field

from .models import Difficulty, Category

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


# ---------- Users ----------

class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    email: EmailStr
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
    following. Lighter than UserProfile (no email, no following_count)
    since these render as rows/cards, not a full profile page."""

    id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    recipe_count: int
    follower_count: int
    is_following: bool = False  # relative to the requesting user, if authenticated


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
    """Lightweight shape for list/feed views."""

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

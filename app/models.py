import enum
from datetime import datetime, timezone
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field
from pymongo import IndexModel, ASCENDING


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Difficulty(str, enum.Enum):
    easy = "Easy"
    medium = "Medium"
    hard = "Hard"


class Category(str, enum.Enum):
    breakfast = "Breakfast"
    lunch = "Lunch"
    dinner = "Dinner"
    dessert = "Dessert"


class User(Document):
    full_name: str
    username: Indexed(str, unique=True)
    email: Indexed(str, unique=True)
    hashed_password: str
    bio: Optional[str] = None
    location: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "users"


class RefreshToken(Document):
    """A DB-backed, revocable refresh token. We never store the raw
    token — only a SHA-256 hash of it — so a database leak alone can't
    be used to mint new access tokens."""

    user_id: str
    token_hash: str
    expires_at: datetime
    revoked: bool = False
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "refresh_tokens"
        indexes = [IndexModel([("token_hash", ASCENDING)], unique=True)]


class Recipe(Document):
    title: str
    image_url: Optional[str] = None
    cook_minutes: int
    difficulty: Difficulty
    category: Category
    rating_avg: float = 0.0
    rating_count: int = 0
    author_id: str
    ingredients: list[str]
    steps: list[str]
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "recipes"
        indexes = ["author_id", "category", "title", "-created_at"]


class Favorite(Document):
    user_id: str
    recipe_id: str
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "favorites"
        indexes = [IndexModel([("user_id", ASCENDING), ("recipe_id", ASCENDING)], unique=True)]


class Review(Document):
    recipe_id: str
    author_id: str
    rating: int  # 1-5
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "reviews"
        indexes = [IndexModel([("author_id", ASCENDING), ("recipe_id", ASCENDING)], unique=True)]


class Follow(Document):
    follower_id: str
    followed_id: str
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "follows"
        indexes = [IndexModel([("follower_id", ASCENDING), ("followed_id", ASCENDING)], unique=True)]


ALL_DOCUMENTS = [User, RefreshToken, Recipe, Favorite, Review, Follow]

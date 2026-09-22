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


class AuthProvider(str, enum.Enum):
    password = "password"
    google = "google"


class User(Document):
    full_name: str
    username: Indexed(str, unique=True)
    email: Indexed(str, unique=True)
    # Optional now: a Google-only account has no local password. Never
    # expose this field outside the auth layer.
    hashed_password: Optional[str] = None
    auth_provider: AuthProvider = AuthProvider.password
    is_email_verified: bool = False
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


class EmailVerificationToken(Document):
    """Same hashed-storage pattern as refresh tokens: the raw token only
    ever exists in the email link itself, never at rest in the DB."""

    user_id: str
    token_hash: str
    expires_at: datetime
    used: bool = False
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "email_verification_tokens"
        indexes = [IndexModel([("token_hash", ASCENDING)], unique=True)]


class DeviceToken(Document):
    """An FCM registration token for one device. A user can have several
    (phone + tablet, or reinstalls), so this is keyed by the token
    itself, not one-per-user."""

    user_id: str
    token: str
    platform: str  # "android" | "ios" | "web" — informational, not enforced
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "device_tokens"
        indexes = [IndexModel([("token", ASCENDING)], unique=True), "user_id"]


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


ALL_DOCUMENTS = [User, RefreshToken, EmailVerificationToken, DeviceToken, Recipe, Favorite, Review, Follow]

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db, close_db, init_firebase
from .routers import auth, recipes, users, notifications
from app.routers import cloudinary


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    init_firebase()
    yield
    await close_db()


app = FastAPI(
    title="Recipe Box API",
    description=(
        "Backend for the Recipe Box app — JWT auth with rotating refresh tokens, "
        "Google OAuth, email verification, recipes, favorites, reviews, follows, "
        "and FCM push notifications. Backed by MongoDB."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(recipes.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(cloudinary.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}

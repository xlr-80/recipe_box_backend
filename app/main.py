from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db, close_db
from .routers import auth, recipes, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="Recipe Box API",
    description="Backend for the Recipe Box app — auth (JWT access + rotating DB-backed refresh tokens), recipes, favorites, reviews, follows. Backed by MongoDB.",
    version="2.0.0",
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


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}

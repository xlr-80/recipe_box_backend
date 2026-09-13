from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from .config import settings
from .models import ALL_DOCUMENTS

_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URI, tz_aware=True)
    await init_beanie(database=_client[settings.MONGO_DB_NAME], document_models=ALL_DOCUMENTS)


async def close_db() -> None:
    if _client is not None:
        _client.close()

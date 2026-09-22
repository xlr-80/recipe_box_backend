import logging

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from .config import settings
from .models import ALL_DOCUMENTS

logger = logging.getLogger("recipebox")

_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URI, tz_aware=True)
    await init_beanie(database=_client[settings.MONGO_DB_NAME], document_models=ALL_DOCUMENTS)


async def close_db() -> None:
    if _client is not None:
        _client.close()


def init_firebase() -> None:
    """Initializes the Firebase Admin SDK if a service account path is
    configured. If not, FCM sending becomes a no-op with a log line —
    device registration still works either way, so the app doesn't
    require Firebase to be set up just to run locally."""
    if not settings.FCM_SERVICE_ACCOUNT_PATH:
        logger.warning("FCM_SERVICE_ACCOUNT_PATH not set — push notifications will be logged, not sent.")
        return

    import firebase_admin
    from firebase_admin import credentials

    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FCM_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)

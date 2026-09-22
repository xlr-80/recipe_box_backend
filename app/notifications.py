import logging

from . import models
from .config import settings

logger = logging.getLogger("recipebox")


async def register_device(user_id: str, token: str, platform: str) -> None:
    """Upserts a device token. Tokens are unique across the whole
    collection (not per-user) since the same token should never belong
    to two users at once — if it does, the old registration is stale
    (e.g. the app was reinstalled under a different account) and gets
    reassigned."""
    existing = await models.DeviceToken.find_one(models.DeviceToken.token == token)
    if existing:
        existing.user_id = user_id
        existing.platform = platform
        await existing.save()
    else:
        await models.DeviceToken(user_id=user_id, token=token, platform=platform).insert()


async def unregister_device(token: str) -> None:
    existing = await models.DeviceToken.find_one(models.DeviceToken.token == token)
    if existing:
        await existing.delete()


async def send_to_user(user_id: str, title: str, body: str, data: dict[str, str] | None = None) -> None:
    """Sends a push notification to every device registered to a user.
    A user with no registered devices, or an unconfigured Firebase
    project, are both silent no-ops — this is meant to be called
    fire-and-forget from other endpoints (new follower, new review)
    without ever failing the request that triggered it."""
    tokens = await models.DeviceToken.find(models.DeviceToken.user_id == user_id).to_list()
    if not tokens:
        return

    if not settings.FCM_SERVICE_ACCOUNT_PATH:
        logger.info("[FCM disabled] Would notify user %s: %s — %s", user_id, title, body)
        return

    import firebase_admin
    from firebase_admin import messaging

    if not firebase_admin._apps:
        logger.warning("FCM_SERVICE_ACCOUNT_PATH is set but Firebase was never initialized — call init_firebase() at startup.")
        return

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        tokens=[t.token for t in tokens],
    )
    response = messaging.send_each_for_multicast(message)

    # Clean up tokens Firebase reports as dead (uninstalled app, expired
    # registration) so the token list doesn't grow stale forever.
    for token_doc, result in zip(tokens, response.responses):
        if not result.success and result.exception is not None:
            error_code = getattr(result.exception, "code", "")
            if error_code in ("NOT_FOUND", "UNREGISTERED"):
                await token_doc.delete()

from fastapi import APIRouter, Depends, status

from .. import models, schemas
from ..dependencies import get_current_user
from .. import notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/register-device", status_code=status.HTTP_200_OK)
async def register_device(payload: schemas.DeviceTokenIn, current_user: models.User = Depends(get_current_user)):
    """Call this after Firebase hands the app an FCM registration token
    — on first launch, and again whenever Firebase reports the token
    has rotated (it does this occasionally)."""
    await notifications.register_device(str(current_user.id), payload.token, payload.platform)
    return {"message": "Device registered"}


@router.delete("/register-device", status_code=status.HTTP_200_OK)
async def unregister_device(payload: schemas.DeviceTokenIn, current_user: models.User = Depends(get_current_user)):
    """Call this on logout so a signed-out device stops receiving pushes
    meant for the account that just logged out."""
    await notifications.unregister_device(payload.token)
    return {"message": "Device unregistered"}

import time

import cloudinary
import cloudinary.utils
from fastapi import APIRouter, Depends

from app import models
from app.config import settings
from app.dependencies import get_current_user


router = APIRouter(
    prefix="/cloudinary",
    tags=["Cloudinary"],
)


@router.post("/signature")
async def create_upload_signature(
    current_user: models.User = Depends(get_current_user),
):
    timestamp = int(time.time())

    signature = cloudinary.utils.api_sign_request(
        {"timestamp": timestamp},
        settings.CLOUDINARY_API_SECRET,
    )

    return {
        "signature": signature,
        "timestamp": timestamp,
        "api_key": settings.CLOUDINARY_API_KEY,
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
    }
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "recipebox"

    SECRET_KEY: str = "change-this-to-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    CORS_ORIGINS: str = "*"

    # Email verification
    EMAIL_BACKEND: str = "console"  # "console" | "smtp"
    EMAIL_FROM: str = "no-reply@recipebox.app"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    REQUIRE_EMAIL_VERIFICATION: bool = False
    EMAIL_VERIFICATION_BASE_URL: str = "https://recipebox.app/verify-email"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""

    # Firebase Cloud Messaging
    FCM_SERVICE_ACCOUNT_PATH: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()

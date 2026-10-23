import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    DATABASE_URL = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/food_delivery"
    )
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    TZ_OFFSET_MINUTES = int(os.getenv("TZ_OFFSET_MINUTES", "330"))
    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", "true")
    SURGE_PRICING_ENABLED = _bool("SURGE_PRICING_ENABLED", "false")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@food.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")


settings = Settings()

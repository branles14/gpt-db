import os
from dotenv import load_dotenv

# Load environment from .env, while allowing real env to override
load_dotenv(override=False)


def get_api_key() -> str | None:
    return os.getenv("API_KEY") or None


def get_port() -> int:
    return int(os.getenv("PORT", "8000"))


def get_mongo_uri() -> str | None:
    return os.getenv("MONGO_URI") or None


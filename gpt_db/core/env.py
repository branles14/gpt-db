import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment from .env, while allowing real env to override
load_dotenv(override=False)


def get_api_key() -> str | None:
    return os.getenv("API_KEY") or None


def get_port() -> int:
    return int(os.getenv("PORT", "8000"))


def get_mongo_uri() -> str | None:
    """Return a MongoDB connection URI.

    Priority:
    1. Use `MONGO_URI` if provided.
    2. Otherwise, assemble from `MONGO_USER`, `MONGO_PASS`, and `MONGO_HOST`.
       Password is URL-encoded for safety.
    """
    uri = os.getenv("MONGO_URI")
    if uri:
        return uri

    user = os.getenv("MONGO_USER")
    password = os.getenv("MONGO_PASS")
    host = os.getenv("MONGO_HOST")
    if user and password and host:
        return (
            f"mongodb+srv://{user}:{quote_plus(password)}@{host}/?"
            "retryWrites=true&w=majority&appName=gpt-db"
        )
    return None

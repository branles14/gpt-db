from fastapi import Header, HTTPException, status

from app.core.env import get_api_key


async def require_api_key(x_api_key: str | None = Header(default=None)):
    api_key = get_api_key()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server not configured: set API_KEY",
        )
    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


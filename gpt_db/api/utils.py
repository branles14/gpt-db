from typing import Any, Dict

from fastapi.responses import JSONResponse


def success_response(
    content: Dict[str, Any] | None = None,
    message: str | None = None,
    status_code: int = 200,
) -> JSONResponse:
    """Standard success envelope used by mutating endpoints.

    Adds a `success: true` flag and optional `message`, merged with provided content.
    """
    base: Dict[str, Any] = {"success": True}
    if message:
        base["message"] = message
    if content:
        base.update(content)
    return JSONResponse(status_code=status_code, content=base)


def error_response(
    message: str,
    status_code: int = 400,
    extra: Dict[str, Any] | None = None,
) -> JSONResponse:
    """Standard error envelope for user-facing errors.

    Adds `success: false` and a simple `error` message, optionally merged with extra fields.
    """
    base: Dict[str, Any] = {"success": False, "error": message}
    if extra:
        base.update(extra)
    return JSONResponse(status_code=status_code, content=base)


def format_mongo_error(exc: Exception) -> Dict[str, Any]:
    """Produce a user-friendly MongoDB error response."""
    message = str(exc)
    if "Authentication failed" in message:
        return {
            "success": False,
            "error": True,
            "type": "DatabaseAuthenticationError",
            "message": (
                "Unable to connect to MongoDB: authentication failed. "
                "Please check your username, password, or connection string."
            ),
            "code": 8000,
            "service": "MongoDB Atlas",
        }
    return {
        "success": False,
        "error": True,
        "type": "DatabaseConnectionError",
        "message": "Failed to connect to MongoDB.",
    }

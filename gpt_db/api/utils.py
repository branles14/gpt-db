from typing import Any, Dict


def format_mongo_error(exc: Exception) -> Dict[str, Any]:
    """Produce a user-friendly MongoDB error response."""
    message = str(exc)
    if "Authentication failed" in message:
        return {
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
        "error": True,
        "type": "DatabaseConnectionError",
        "message": "Failed to connect to MongoDB.",
    }

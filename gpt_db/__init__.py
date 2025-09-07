"""gpt_db package init.

Avoid re-exporting the FastAPI application object here to prevent
import-order cycles when the serverless runtime imports `gpt_db.app`
as the entrypoint while submodules import from `gpt_db`.
"""

__all__ = []


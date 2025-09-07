from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from gpt_db.api.deps import require_api_key
from gpt_db.health import mongo_status

router = APIRouter()


@router.get("/health", dependencies=[Depends(require_api_key)])
async def health() -> JSONResponse:
    """Report service health information."""
    mongo = await mongo_status()
    status_code = (
        status.HTTP_200_OK if mongo.get("status") == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content={"mongo": mongo})

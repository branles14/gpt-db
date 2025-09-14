from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from gpt_db.api.deps import require_api_key
from .service import mongo_status

router = APIRouter()


@router.get("/api/health", dependencies=[Depends(require_api_key)])
async def health() -> JSONResponse:
    """Report service health information."""
    mongo = await mongo_status()
    components = {
        "mongo": "ok" if mongo.get("status") == "ok" else mongo,
    }
    overall_status = "ok" if components["mongo"] == "ok" else "error"
    status_code = (
        status.HTTP_200_OK
        if overall_status == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(
        status_code=status_code,
        content={"status": overall_status, "components": components},
    )

from fastapi import APIRouter, Depends

from gpt_db.api.deps import require_api_key
from gpt_db.api.catalog import router as catalog_router
from gpt_db.api.health import router as health_router
from gpt_db.api.log import router as log_router
from gpt_db.api.stock import router as stock_router
from gpt_db.api.targets import router as targets_router

router = APIRouter()
router.include_router(catalog_router)
router.include_router(stock_router)
router.include_router(log_router)
router.include_router(targets_router)
router.include_router(health_router)


@router.get("/", dependencies=[Depends(require_api_key)])
async def root():
    return {"message": "🍌"}




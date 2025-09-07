from fastapi import APIRouter

from .stock import router as stock_router
from .catalog import router as catalog_router
from .log import router as log_router

router = APIRouter()
router.include_router(stock_router)
router.include_router(catalog_router)
router.include_router(log_router)

__all__ = ["router"]

from fastapi import APIRouter

from .entries import router as entries_router
from .targets import router as targets_router

router = APIRouter()
router.include_router(entries_router)
router.include_router(targets_router)

__all__ = ["router"]


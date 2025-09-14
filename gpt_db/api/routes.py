from fastapi import APIRouter, Depends

from gpt_db.api.deps import require_api_key
from gpt_db.api.food import router as food_router
from gpt_db.api.health import router as health_router

router = APIRouter()
router.include_router(food_router)  # includes stock and catalog
router.include_router(health_router)


@router.get("/", dependencies=[Depends(require_api_key)])
async def root():
    return {"message": "🍌"}




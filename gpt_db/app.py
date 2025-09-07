from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse

from gpt_db.api.deps import require_api_key
from gpt_db.api.routes import router
from gpt_db.db.mongo import close_mongo_client, get_mongo_client


def create_app() -> FastAPI:
    application = FastAPI(
        title="gpt-db", docs_url=None, redoc_url=None, openapi_url=None
    )

    @application.on_event("startup")
    async def startup_event() -> None:
        """Initialize resources on startup."""
        get_mongo_client()

    @application.on_event("shutdown")
    async def shutdown_event() -> None:
        """Clean up resources on shutdown."""
        close_mongo_client()

    application.include_router(router)

    @application.get("/openapi.json", include_in_schema=False)
    async def openapi() -> JSONResponse:
        return JSONResponse(application.openapi())

    @application.get("/docs", include_in_schema=False)
    async def swagger_ui_html():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

    @application.get("/redoc", dependencies=[Depends(require_api_key)], include_in_schema=False)
    async def redoc_html():
        return get_redoc_html(openapi_url="/openapi.json", title="redoc")

    return application


app = create_app()


from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse

from gpt_db.api.deps import require_api_key
from gpt_db.api.routes import router


def create_app() -> FastAPI:
    application = FastAPI(
        title="gpt-db", docs_url=None, redoc_url=None, openapi_url=None
    )
    application.include_router(router)

    @application.get(
        "/openapi.json",
        dependencies=[Depends(require_api_key)],
        include_in_schema=False,
    )
    async def openapi() -> JSONResponse:
        return JSONResponse(application.openapi())

    @application.get("/docs", dependencies=[Depends(require_api_key)], include_in_schema=False)
    async def swagger_ui_html():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

    @application.get("/redoc", dependencies=[Depends(require_api_key)], include_in_schema=False)
    async def redoc_html():
        return get_redoc_html(openapi_url="/openapi.json", title="redoc")

    return application


app = create_app()


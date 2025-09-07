from fastapi import FastAPI

from app.api.routes import router


def create_app() -> FastAPI:
    application = FastAPI(title="gpt-db")
    application.include_router(router)
    return application


app = create_app()


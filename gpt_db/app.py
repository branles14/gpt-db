from fastapi import FastAPI

from gpt_db.api.routes import router


def create_app() -> FastAPI:
    application = FastAPI(title="gpt-db")
    application.include_router(router)
    return application


app = create_app()


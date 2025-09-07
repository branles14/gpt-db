import os
from fastapi.testclient import TestClient

from gpt_db.app import create_app


def test_docs_and_openapi_accessible_without_auth():
    os.environ.setdefault("API_KEY", "secret")
    os.environ.setdefault("MONGO_URI", "mongodb://example.com")
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/redoc").status_code == 401


import os
from fastapi.testclient import TestClient

from gpt_db.app import create_app


def test_patch_targets_has_schema_properties():
    os.environ.setdefault("API_KEY", "secret")
    os.environ.setdefault("MONGO_URI", "mongodb://example.com")
    app = create_app()
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        patch_schema = schema["paths"]["/food/targets"]["patch"]["requestBody"]["content"]["application/json"]["schema"]
        if "$ref" in patch_schema:
            ref_name = patch_schema["$ref"].split("/")[-1]
            patch_schema = schema["components"]["schemas"][ref_name]
        assert patch_schema.get("properties"), "expected properties in patch schema"

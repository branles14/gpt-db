import httpx

from mock_mongo import create_client


def mock_openfoodfacts(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)


def test_add_stock_fetches_and_inserts_product(monkeypatch):
    def handler(request):
        data = {
            "status": 1,
            "product": {
                "product_name": "Mocked Product",
                "categories_tags": ["en:snacks"],
                "ingredients_text": "Sugar, Salt",
                "nutriments": {
                    "energy-kcal_100g": 100,
                    "proteins_100g": 5,
                    "fat_100g": 1,
                    "carbohydrates_100g": 20,
                    "fiber_100g": 3,
                    "sugars_100g": 10,
                },
            },
        }
        return httpx.Response(200, json=data)

    mock_openfoodfacts(monkeypatch, handler)
    payload = {"items": [{"upc": "12345", "quantity": 2}]}
    with create_client(monkeypatch) as client:
        resp = client.post("/food/stock", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201

        cat_resp = client.get("/food/catalog", headers={"x-api-key": "secret"})
        item = cat_resp.json()["items"][0]
        assert item["name"] == "Mocked Product"
        assert item["upc"] == "12345"
        assert "snacks" in item["tags"]
        assert "Sugar" in item["ingredients"]
        assert item["nutrition"]["calories"] == 100

        stock_resp = client.get("/food/stock?view=items", headers={"x-api-key": "secret"})
        stock_item = stock_resp.json()["items"][0]
        assert stock_item["upc"] == "12345"
        assert stock_item["quantity"] == 2
        assert stock_item["product_id"] == item["_id"]


def test_add_stock_off_404(monkeypatch):
    def handler(request):
        return httpx.Response(404)

    mock_openfoodfacts(monkeypatch, handler)
    payload = {"items": [{"upc": "12345", "quantity": 1}]}
    with create_client(monkeypatch) as client:
        resp = client.post("/food/stock", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201

        cat_resp = client.get("/food/catalog", headers={"x-api-key": "secret"})
        item = cat_resp.json()["items"][0]
        assert item["upc"] == "12345"
        assert "name" not in item

        stock_resp = client.get("/food/stock?view=items", headers={"x-api-key": "secret"})
        stock_item = stock_resp.json()["items"][0]
        assert stock_item["product_id"] == item["_id"]


def test_add_stock_off_network_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    mock_openfoodfacts(monkeypatch, handler)
    payload = {"items": [{"upc": "12345", "quantity": 1}]}
    with create_client(monkeypatch) as client:
        resp = client.post("/food/stock", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201

        cat_resp = client.get("/food/catalog", headers={"x-api-key": "secret"})
        item = cat_resp.json()["items"][0]
        assert item["upc"] == "12345"
        assert "name" not in item

        stock_resp = client.get("/food/stock?view=items", headers={"x-api-key": "secret"})
        stock_item = stock_resp.json()["items"][0]
        assert stock_item["product_id"] == item["_id"]

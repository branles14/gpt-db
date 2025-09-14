from mock_mongo import create_client


def test_unknown_nutrition_key_returns_422(monkeypatch):
    payload = {"name": "Mystery", "nutrition": {"per_serving": {"calories": 10, "bogus": 1}}}
    with create_client(monkeypatch) as client:
        resp = client.post("/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 422


def test_empty_nutrition_defaults_to_zero(monkeypatch):
    payload = {"name": "Empty", "nutrition": {"per_serving": {}}}
    with create_client(monkeypatch) as client:
        resp = client.post("/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201
        item = resp.json()["item"]
        assert all(v == 0 for v in item["nutrition"]["per_serving"].values())


def test_partial_nutrition_defaults_to_zero(monkeypatch):
    payload = {"name": "Partial", "nutrition": {"per_serving": {"calories": 10}}}
    with create_client(monkeypatch) as client:
        resp = client.post("/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201
        item = resp.json()["item"]
        assert item["nutrition"]["per_serving"]["calories"] == 10
        for k, v in item["nutrition"]["per_serving"].items():
            if k != "calories":
                assert v == 0


def test_full_nutrition_persists(monkeypatch):
    nutrition = {
        "calories": 100,
        "protein": 5,
        "fat": 1,
        "carbs": 20,
        "fiber": 3,
        "sugars": 10,
        "saturated_fat": 0.5,
        "trans_fat": 0.0,
        "cholesterol_mg": 1,
        "sodium_mg": 2,
        "potassium_mg": 3,
        "calcium_mg": 4,
        "iron_mg": 5,
        "magnesium_mg": 6,
        "phosphorus_mg": 7,
        "zinc_mg": 8,
        "selenium_mcg": 9,
        "copper_mg": 10,
        "manganese_mg": 11,
        "vitamin_a_mcg": 12,
        "vitamin_c_mg": 13,
        "vitamin_d_mcg": 14,
        "vitamin_e_mg": 15,
        "vitamin_k_mcg": 16,
        "thiamin_mg": 17,
        "riboflavin_mg": 18,
        "niacin_mg": 19,
        "vitamin_b6_mg": 20,
        "folate_mcg": 21,
        "vitamin_b12_mcg": 22,
    }
    payload = {"name": "Complete", "nutrition": {"per_serving": nutrition}}
    with create_client(monkeypatch) as client:
        resp = client.post("/catalog", json=payload, headers={"x-api-key": "secret"})
        assert resp.status_code == 201

        list_resp = client.get("/catalog", headers={"x-api-key": "secret"})
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert any(
            item["name"] == "Complete" and item["nutrition"]["per_serving"] == nutrition
            for item in items
        )


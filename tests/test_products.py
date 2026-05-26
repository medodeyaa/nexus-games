def test_list_all_products(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"]
    assert len(body["products"]) == 3


def test_filter_by_category(client):
    r = client.get("/api/products?category=RPG")
    body = r.get_json()
    assert all(p["category"] == "RPG" for p in body["products"])
    assert len(body["products"]) == 1


def test_filter_by_price_range(client):
    r = client.get("/api/products?min_price=20&max_price=40")
    body = r.get_json()
    assert all(20 <= p["price"] <= 40 for p in body["products"])


def test_search(client):
    r = client.get("/api/products?search=cheap")
    body = r.get_json()
    assert len(body["products"]) == 1
    assert "Cheap" in body["products"][0]["title"]


def test_sort_price_asc(client):
    r = client.get("/api/products?sort=price_asc")
    prices = [p["price"] for p in r.get_json()["products"]]
    assert prices == sorted(prices)


def test_sort_price_desc(client):
    r = client.get("/api/products?sort=price_desc")
    prices = [p["price"] for p in r.get_json()["products"]]
    assert prices == sorted(prices, reverse=True)


def test_get_one(client):
    r = client.get("/api/products/1")
    assert r.get_json()["product"]["title"] == "Test RPG"


def test_get_missing(client):
    r = client.get("/api/products/999")
    assert r.status_code == 404


def test_categories_list(client):
    r = client.get("/api/products/categories")
    cats = r.get_json()["categories"]
    assert set(cats) == {"RPG", "Adventure", "Indie"}

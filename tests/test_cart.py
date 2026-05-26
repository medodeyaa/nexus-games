def csrf(c):
    return c.get("/api/user").get_json()["csrf_token"]


def test_cart_requires_auth(client):
    r = client.get("/api/cart")
    assert r.status_code == 401


def test_add_and_list_cart(alice_client):
    token = csrf(alice_client)
    r = alice_client.post("/api/cart", json={"product_id": 1}, headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]
    r = alice_client.get("/api/cart")
    body = r.get_json()
    assert body["count"] == 1
    assert body["total"] == 49.99


def test_remove_cart_item(alice_client):
    token = csrf(alice_client)
    alice_client.post("/api/cart", json={"product_id": 1}, headers={"X-CSRF-Token": token})
    cart = alice_client.get("/api/cart").get_json()
    cart_item_id = cart["items"][0]["cart_item_id"]
    r = alice_client.delete(f"/api/cart/{cart_item_id}", headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]
    assert alice_client.get("/api/cart").get_json()["count"] == 0


def test_clear_cart(alice_client):
    token = csrf(alice_client)
    alice_client.post("/api/cart", json={"product_id": 1}, headers={"X-CSRF-Token": token})
    alice_client.post("/api/cart", json={"product_id": 3}, headers={"X-CSRF-Token": token})
    r = alice_client.delete("/api/cart", headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]
    assert alice_client.get("/api/cart").get_json()["count"] == 0


def test_add_out_of_stock_rejected(alice_client):
    token = csrf(alice_client)
    r = alice_client.post("/api/cart", json={"product_id": 2}, headers={"X-CSRF-Token": token})
    assert r.status_code == 400


def test_csrf_required_for_add(alice_client):
    r = alice_client.post("/api/cart", json={"product_id": 1})
    assert r.status_code == 403

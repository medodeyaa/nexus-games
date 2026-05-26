def csrf(c):
    return c.get("/api/user").get_json()["csrf_token"]


def test_admin_endpoints_reject_non_admin(alice_client):
    assert alice_client.get("/api/admin/stats").status_code == 403
    assert alice_client.get("/api/admin/products").status_code == 403
    assert alice_client.get("/api/admin/orders").status_code == 403
    assert alice_client.get("/api/admin/users").status_code == 403


def test_admin_endpoints_reject_anonymous(client):
    assert client.get("/api/admin/stats").status_code == 401


def test_admin_can_view_stats(admin_client):
    r = admin_client.get("/api/admin/stats")
    body = r.get_json()
    assert body["success"]
    assert body["stats"]["users"] == 2
    assert body["stats"]["products"] == 3


def test_admin_can_create_product(admin_client):
    token = csrf(admin_client)
    r = admin_client.post("/api/admin/products", json={
        "title": "New Game", "price": 19.99, "category": "Puzzle",
        "description": "Test", "image": "x.jpg", "stock": 50,
    }, headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]
    new_id = r.get_json()["id"]
    r = admin_client.get(f"/api/products/{new_id}")
    assert r.get_json()["product"]["title"] == "New Game"


def test_admin_can_update_product(admin_client):
    token = csrf(admin_client)
    r = admin_client.put("/api/admin/products/1", json={"price": 99.99},
                         headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]
    assert admin_client.get("/api/products/1").get_json()["product"]["price"] == 99.99


def test_admin_can_delete_product(admin_client):
    token = csrf(admin_client)
    r = admin_client.delete("/api/admin/products/3", headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]
    assert admin_client.get("/api/products/3").status_code == 404


def test_admin_can_promote_user(admin_client):
    token = csrf(admin_client)
    r = admin_client.put("/api/admin/users/2", json={"is_admin": True},
                         headers={"X-CSRF-Token": token})
    assert r.get_json()["success"]


def test_admin_cannot_demote_self(admin_client):
    token = csrf(admin_client)
    r = admin_client.put("/api/admin/users/1", json={"is_admin": False},
                         headers={"X-CSRF-Token": token})
    assert r.status_code == 400

def csrf(c):
    return c.get("/api/user").get_json()["csrf_token"]


def _seed_cart(alice_client, product_ids):
    token = csrf(alice_client)
    for pid in product_ids:
        alice_client.post("/api/cart", json={"product_id": pid}, headers={"X-CSRF-Token": token})
    return token


def test_checkout_requires_full_form(alice_client):
    token = _seed_cart(alice_client, [1])
    r = alice_client.post(
        "/api/checkout/create-session",
        json={"full_name": "A", "email": "bad", "shipping_address": ""},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 400


def test_checkout_creates_pending_order_without_stripe(alice_client, app_module):
    """Even without Stripe keys, the pending order should be created."""
    app_module.stripe = None  # disable real Stripe call
    app_module.STRIPE_AVAILABLE = False
    token = _seed_cart(alice_client, [1, 3])
    r = alice_client.post(
        "/api/checkout/create-session",
        json={"full_name": "Alice Tester", "email": "alice@test.local",
              "shipping_address": "123 Test Lane"},
        headers={"X-CSRF-Token": token},
    )
    body = r.get_json()
    assert "order_id" in body
    order_id = body["order_id"]

    # Order should exist and belong to Alice
    detail = alice_client.get(f"/api/orders/{order_id}").get_json()
    assert detail["order"]["id"] == order_id
    # Server-recomputed total = 49.99 + 9.99 = 59.98
    assert abs(detail["order"]["total"] - 59.98) < 0.01


def test_orders_only_visible_to_owner(alice_client, app_module):
    """Bob shouldn't see Alice's order."""
    app_module.STRIPE_AVAILABLE = False
    token = _seed_cart(alice_client, [1])
    r = alice_client.post(
        "/api/checkout/create-session",
        json={"full_name": "Alice", "email": "alice@test.local",
              "shipping_address": "123 Test Lane"},
        headers={"X-CSRF-Token": token},
    )
    order_id = r.get_json()["order_id"]

    # Register and log in as Bob
    bob = app_module.app.test_client()
    bob.post("/api/register", json={
        "username": "bobby", "email": "bobby@test.local",
        "password": "BobPass1234", "confirm_password": "BobPass1234",
    })
    bob.post("/api/login", json={"username": "bobby", "password": "BobPass1234"})
    r = bob.get(f"/api/orders/{order_id}")
    assert r.status_code == 403


def test_list_my_orders_empty_initially(alice_client):
    r = alice_client.get("/api/orders")
    body = r.get_json()
    assert body["success"]
    assert body["orders"] == []

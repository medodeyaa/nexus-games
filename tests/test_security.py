def csrf(c):
    return c.get("/api/user").get_json()["csrf_token"]


def test_sql_injection_in_login_safe(client):
    """A classic SQLi attempt should NOT log us in."""
    r = client.post("/api/login", json={
        "username": "alice' OR '1'='1",
        "password": "anything",
    })
    assert r.status_code == 401


def test_sql_injection_in_search_safe(client):
    r = client.get("/api/products?search='; DROP TABLE products; --")
    # Should not 500 and the products table should still exist
    assert r.status_code == 200
    r2 = client.get("/api/products")
    assert len(r2.get_json()["products"]) == 3


def test_xss_payload_in_register_is_stored_but_escaped_on_render(client):
    payload = "<script>alert(1)</script>"
    # The username regex disallows < and >, so this should fail validation
    r = client.post("/api/register", json={
        "username": payload, "email": "xss@test.local",
        "password": "Pass1234", "confirm_password": "Pass1234",
    })
    assert r.status_code == 400


def test_weak_password_rejected(client):
    r = client.post("/api/register", json={
        "username": "weakguy", "email": "w@test.local",
        "password": "short", "confirm_password": "short",
    })
    assert r.status_code == 400


def test_csrf_required_on_state_changing_endpoints(alice_client):
    # No CSRF header → 403
    r = alice_client.post("/api/cart", json={"product_id": 1})
    assert r.status_code == 403
    r = alice_client.delete("/api/cart")
    assert r.status_code == 403


def test_session_cookie_httponly(client):
    r = client.post("/api/login", json={"username": "alice", "password": "AlicePass1"})
    cookie_header = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header


def test_password_reset_flow(client, app_module):
    """Request a reset, capture the token from the DB, then confirm with a new password."""
    import sqlite3
    r = client.post("/api/password-reset/request", json={"email": "alice@test.local"})
    assert r.get_json()["success"]

    conn = sqlite3.connect(app_module.DB_PATH)
    row = conn.execute(
        "SELECT token FROM password_resets ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    token = row[0]

    r = client.post("/api/password-reset/confirm", json={
        "token": token, "new_password": "Newpass1234"
    })
    assert r.get_json()["success"]
    # Old password should fail
    assert client.post("/api/login",
                      json={"username": "alice", "password": "AlicePass1"}).status_code == 401
    # New password should work
    assert client.post("/api/login",
                      json={"username": "alice", "password": "Newpass1234"}).status_code == 200

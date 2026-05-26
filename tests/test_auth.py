def test_register_and_login(client):
    r = client.post("/api/register", json={
        "username": "bob",
        "email": "bob@test.local",
        "password": "BobPass123",
        "confirm_password": "BobPass123",
    })
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    r = client.post("/api/login", json={"username": "bob", "password": "BobPass123"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    r = client.get("/api/user")
    assert r.get_json()["logged_in"] is True


def test_register_rejects_short_username(client):
    r = client.post("/api/register", json={
        "username": "ab", "email": "a@b.com",
        "password": "Pass1234", "confirm_password": "Pass1234",
    })
    assert r.status_code == 400


def test_register_rejects_bad_email(client):
    r = client.post("/api/register", json={
        "username": "bobby", "email": "not-an-email",
        "password": "Pass1234", "confirm_password": "Pass1234",
    })
    assert r.status_code == 400


def test_register_rejects_weak_password(client):
    r = client.post("/api/register", json={
        "username": "bobby", "email": "bobby@test.local",
        "password": "weakpass", "confirm_password": "weakpass",
    })
    assert r.status_code == 400


def test_register_password_mismatch(client):
    r = client.post("/api/register", json={
        "username": "bobby", "email": "bobby@test.local",
        "password": "Pass1234", "confirm_password": "Other1234",
    })
    assert r.status_code == 400


def test_duplicate_username_rejected(client):
    r = client.post("/api/register", json={
        "username": "alice", "email": "x@x.com",
        "password": "Pass1234", "confirm_password": "Pass1234",
    })
    assert r.status_code == 400


def test_wrong_password_login(client):
    r = client.post("/api/login", json={"username": "alice", "password": "WrongPass1"})
    assert r.status_code == 401


def test_logout_clears_session(alice_client):
    alice_client.get("/api/logout")
    r = alice_client.get("/api/user")
    assert r.get_json()["logged_in"] is False

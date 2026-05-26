"""Shared pytest fixtures: ephemeral DB per test, Flask test client, auth helpers."""
import os
import sys
import tempfile
import sqlite3
import pytest
from werkzeug.security import generate_password_hash

# Make the project root importable
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)


@pytest.fixture
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def app_module(temp_db, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    # Fresh schema + minimal seed
    with open(os.path.join(ROOT, "schema.sql"), "r", encoding="utf-8") as f:
        schema = f.read()
    conn = sqlite3.connect(temp_db)
    conn.executescript(schema)
    conn.executemany(
        "INSERT INTO products (id, title, price, category, description, image, stock) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "Test RPG", 49.99, "RPG", "A test RPG", "photos/test.jpg", 5),
            (2, "Test Adventure", 29.99, "Adventure", "A test adventure", "photos/t2.jpg", 0),
            (3, "Cheap Game", 9.99, "Indie", "Budget pick", "photos/t3.jpg", 100),
        ],
    )
    conn.execute(
        "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, 1)",
        ("admin", "admin@test.local", generate_password_hash("AdminPass1")),
    )
    conn.execute(
        "INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, 0)",
        ("alice", "alice@test.local", generate_password_hash("AlicePass1")),
    )
    conn.commit()
    conn.close()

    # Import after env is patched so DATABASE_PATH is read fresh
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod  # noqa: WPS433
    app_mod.DB_PATH = temp_db
    app_mod.app.config["TESTING"] = True
    return app_mod


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


def _login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


def _csrf(client):
    r = client.get("/api/user")
    return r.get_json()["csrf_token"]


@pytest.fixture
def alice_client(app_module):
    c = app_module.app.test_client()
    _login(c, "alice", "AlicePass1")
    return c


@pytest.fixture
def admin_client(app_module):
    c = app_module.app.test_client()
    _login(c, "admin", "AdminPass1")
    return c


@pytest.fixture
def csrf_for():
    return _csrf

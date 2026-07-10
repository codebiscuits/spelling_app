import pytest

from tests.conftest import TEST_PASSWORD, login


# ── Index redirects ────────────────────────────────────────────────────────

def test_index_redirects_anonymous_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.headers["location"] == "/login"


def test_index_redirects_admin_to_admin_dashboard(admin_client):
    resp = admin_client.get("/", follow_redirects=False)
    assert resp.headers["location"] == "/admin/"


def test_index_redirects_child_to_child_dashboard(child_client):
    resp = child_client.get("/", follow_redirects=False)
    assert resp.headers["location"] == "/child/dashboard"


# ── Login ──────────────────────────────────────────────────────────────────

def test_login_page_renders_with_csrf_field(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'name="csrf_token"' in resp.text


def test_admin_login_succeeds(client):
    resp = login(client, "admin", TEST_PASSWORD)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/"


def test_child_login_succeeds(child_client):
    # child_client fixture itself asserts the login redirect
    resp = child_client.get("/child/dashboard")
    assert resp.status_code == 200
    assert "Alice" in resp.text


def test_login_rejects_wrong_password(child_client):
    child_client.get("/logout")
    resp = login(child_client, "Alice", "wrong password")
    assert resp.headers["location"] == "/login?error=1"


def test_login_rejects_unknown_user(client):
    resp = login(client, "Nobody", TEST_PASSWORD)
    assert resp.headers["location"] == "/login?error=1"


def test_login_error_message_shown(client):
    resp = client.get("/login?error=1")
    assert "Wrong name or password" in resp.text


def test_login_rejects_missing_csrf(client):
    resp = client.post(
        "/login",
        data={"username": "admin", "password": TEST_PASSWORD, "csrf_token": "bogus"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_admin_password_not_usable_for_child_route(admin_client):
    """An admin session must not grant access to child pages."""
    resp = admin_client.get("/child/dashboard", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"


def test_child_cannot_access_admin(child_client):
    resp = child_client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"


# ── Logout ─────────────────────────────────────────────────────────────────

def test_logout_clears_session(child_client):
    child_client.get("/logout", follow_redirects=False)
    resp = child_client.get("/child/dashboard", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"


# ── Guarded routes redirect anonymous users ────────────────────────────────

@pytest.mark.parametrize("path", [
    "/child/dashboard",
    "/child/games/circles.html",
    "/test/start",
    "/test/word",
    "/test/results",
    "/admin/",
    "/admin/lists",
    "/admin/children/new",
])
def test_guarded_routes_redirect_anonymous(client, path):
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from auth import (
    hash_password,
    verify_password,
    get_current_user,
    require_child,
    require_admin,
    generate_csrf_token,
    verify_csrf_token,
)


def fake_request(session=None):
    return SimpleNamespace(session=session if session is not None else {})


# ── Passwords ──────────────────────────────────────────────────────────────

def test_hash_and_verify_roundtrip():
    hashed = hash_password("s3cret")
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed) is True


def test_verify_rejects_wrong_password():
    hashed = hash_password("s3cret")
    assert verify_password("wrong", hashed) is False


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


# ── Session guards ─────────────────────────────────────────────────────────

def test_get_current_user_returns_session_user():
    user = {"user_id": 1, "is_admin": False}
    assert get_current_user(fake_request({"user": user})) == user


def test_get_current_user_returns_none_when_anonymous():
    assert get_current_user(fake_request()) is None


def test_require_child_allows_child():
    user = {"user_id": 1, "is_admin": False, "name": "Alice"}
    assert require_child(fake_request({"user": user})) == user


def test_require_child_redirects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_child(fake_request())
    assert exc.value.status_code == 307
    assert exc.value.headers["Location"] == "/login"


def test_require_child_rejects_admin():
    with pytest.raises(HTTPException) as exc:
        require_child(fake_request({"user": {"user_id": None, "is_admin": True}}))
    assert exc.value.status_code == 307


def test_require_admin_allows_admin():
    user = {"user_id": None, "is_admin": True, "name": "Admin"}
    assert require_admin(fake_request({"user": user})) == user


def test_require_admin_redirects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_admin(fake_request())
    assert exc.value.status_code == 307
    assert exc.value.headers["Location"] == "/login"


def test_require_admin_rejects_child():
    with pytest.raises(HTTPException) as exc:
        require_admin(fake_request({"user": {"user_id": 1, "is_admin": False}}))
    assert exc.value.status_code == 307


# ── CSRF ───────────────────────────────────────────────────────────────────

def test_generate_stores_token_in_session():
    request = fake_request()
    token = generate_csrf_token(request)
    assert request.session["csrf_token"] == token
    assert len(token) == 64  # 32 bytes hex


def test_verify_accepts_matching_token():
    request = fake_request()
    token = generate_csrf_token(request)
    verify_csrf_token(request, token)  # should not raise


def test_verify_rejects_mismatched_token():
    request = fake_request()
    generate_csrf_token(request)
    with pytest.raises(HTTPException) as exc:
        verify_csrf_token(request, "not-the-token")
    assert exc.value.status_code == 403


def test_verify_rejects_when_no_token_in_session():
    with pytest.raises(HTTPException) as exc:
        verify_csrf_token(fake_request(), "anything")
    assert exc.value.status_code == 403

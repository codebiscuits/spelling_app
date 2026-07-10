import secrets
import bcrypt
from fastapi import Request, HTTPException


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_current_user(request: Request):
    return request.session.get("user")


def require_child(request: Request):
    user = request.session.get("user")
    if not user or user.get("is_admin"):
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def require_admin(request: Request):
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


# --- CSRF ---

def generate_csrf_token(request: Request) -> str:
    token = secrets.token_hex(32)
    request.session["csrf_token"] = token
    return token


def verify_csrf_token(request: Request, form_token: str):
    session_token = request.session.get("csrf_token")
    if not session_token or not secrets.compare_digest(session_token, form_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

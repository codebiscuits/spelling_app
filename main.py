import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from database import get_db, init_db
from auth import verify_password, generate_csrf_token, verify_csrf_token
from seed.curriculum_words import seed
from templates_env import templates
from routers import admin as admin_router
from routers import child as child_router
from routers import spelling as spelling_router

load_dotenv()

# ── App setup ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with get_db() as db:
        seed(db)
    yield

app = FastAPI(lifespan=lifespan)

secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    raise RuntimeError("SECRET_KEY not set in environment")

app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    https_only=os.getenv("HTTPS_ONLY", "true").lower() == "true",
    same_site="lax",
    max_age=86400 * 7,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/mini-games", StaticFiles(directory="mini_games"), name="mini_games")

app.include_router(admin_router.router)
app.include_router(child_router.router)
app.include_router(spelling_router.router)


# ── Login / Logout ─────────────────────────────────────────────────────────

@app.get("/")
def index(request: Request):
    user = request.session.get("user")
    if user:
        if user.get("is_admin"):
            return RedirectResponse("/admin/")
        return RedirectResponse("/child/dashboard")
    return RedirectResponse("/login")


@app.get("/login")
def login_form(request: Request):
    csrf = generate_csrf_token(request)
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "login.html", {
        "csrf_token": csrf, "error": error
    })


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    verify_csrf_token(request, csrf_token)

    admin_username = os.getenv("ADMIN_USERNAME", "")
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH", "")

    # Check admin
    if username == admin_username and admin_password_hash:
        if verify_password(password, admin_password_hash):
            request.session["user"] = {"user_id": None, "is_admin": True, "name": "Admin"}
            return RedirectResponse("/admin/", status_code=303)

    # Check child (name-based login)
    with get_db() as db:
        child = db.execute(
            "SELECT * FROM users WHERE name=? AND is_admin=0", (username.strip(),)
        ).fetchone()
        if child and verify_password(password, child["password_hash"]):
            request.session["user"] = {
                "user_id": child["id"],
                "is_admin": False,
                "name": child["name"],
            }
            return RedirectResponse("/child/dashboard", status_code=303)

    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

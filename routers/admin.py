from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone

from database import get_db
from auth import require_admin, hash_password, generate_csrf_token, verify_csrf_token
from templates_env import templates, MINI_GAMES, REWARD_GAMES
from services.game_rewards import unlocked_files

router = APIRouter(prefix="/admin")


def parse_year_group(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


# ── Dashboard ──────────────────────────────────────────────────────────────

@router.get("/")
def admin_dashboard(request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        lists = db.execute("SELECT * FROM word_lists ORDER BY year_group, name").fetchall()
        children = db.execute("SELECT * FROM users WHERE is_admin=0 ORDER BY name").fetchall()
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "lists": lists, "children": children, "csrf_token": csrf,
        "mini_games_list": MINI_GAMES,
    })


# ── Word Lists ─────────────────────────────────────────────────────────────

@router.get("/lists")
def list_word_lists(request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        lists = db.execute("SELECT * FROM word_lists ORDER BY year_group, name").fetchall()
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/word_lists.html", {
        "lists": lists, "csrf_token": csrf
    })


@router.post("/lists/create")
def create_word_list(
    request: Request,
    name: str = Form(...),
    year_group: str = Form(""),
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    yg = parse_year_group(year_group)
    with get_db() as db:
        db.execute("INSERT INTO word_lists (name, year_group) VALUES (?, ?)", (name.strip(), yg))
    return RedirectResponse("/admin/lists", status_code=303)


@router.get("/lists/{list_id}/edit")
def edit_word_list_form(list_id: int, request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        lst = db.execute("SELECT * FROM word_lists WHERE id=?", (list_id,)).fetchone()
        if not lst:
            raise HTTPException(404)
        words = db.execute(
            "SELECT * FROM words WHERE list_id=? ORDER BY word", (list_id,)
        ).fetchall()
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/edit_word_list.html", {
        "list": lst, "words": words, "csrf_token": csrf
    })


@router.post("/lists/{list_id}/edit")
def edit_word_list(
    list_id: int,
    request: Request,
    name: str = Form(...),
    year_group: str = Form(""),
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    yg = parse_year_group(year_group)
    with get_db() as db:
        db.execute(
            "UPDATE word_lists SET name=?, year_group=? WHERE id=?",
            (name.strip(), yg, list_id),
        )
    return RedirectResponse(f"/admin/lists/{list_id}/edit", status_code=303)


@router.post("/lists/{list_id}/delete")
def delete_word_list(
    list_id: int,
    request: Request,
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    with get_db() as db:
        # Legacy single-list sessions reference the list without ON DELETE;
        # detach them so they survive as "Mixed practice" rather than
        # blocking the delete with a foreign-key error
        db.execute("UPDATE test_sessions SET list_id=NULL WHERE list_id=?", (list_id,))
        db.execute("DELETE FROM word_lists WHERE id=?", (list_id,))
    return RedirectResponse("/admin/lists", status_code=303)


@router.post("/lists/{list_id}/words/add")
def add_word(
    list_id: int,
    request: Request,
    word: str = Form(...),
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO words (word, list_id) VALUES (?, ?)",
            (word.strip().lower(), list_id),
        )
    return RedirectResponse(f"/admin/lists/{list_id}/edit", status_code=303)


@router.post("/lists/{list_id}/words/{word_id}/delete")
def delete_word(
    list_id: int,
    word_id: int,
    request: Request,
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    with get_db() as db:
        db.execute("DELETE FROM words WHERE id=? AND list_id=?", (word_id, list_id))
    return RedirectResponse(f"/admin/lists/{list_id}/edit", status_code=303)


# ── Children ───────────────────────────────────────────────────────────────

@router.get("/children/new")
def new_child_form(request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        lists = db.execute("SELECT * FROM word_lists ORDER BY year_group, name").fetchall()
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/edit_child.html", {
        "child": None, "lists": lists, "unlocked_ids": [], "csrf_token": csrf
    })


@router.post("/children/new")
def create_child(
    request: Request,
    name: str = Form(...),
    dob: str = Form(...),
    password: str = Form(...),
    unlock_lists: list[int] = Form(default=[]),
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    now = datetime.now(timezone.utc).isoformat()
    ph = hash_password(password)
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            (name.strip(), dob, ph, now),
        )
        user_id = cur.lastrowid
        for lid in unlock_lists:
            db.execute(
                "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
                (user_id, lid, now),
            )
    return RedirectResponse("/admin/", status_code=303)


@router.get("/children/{child_id}")
def child_detail(child_id: int, request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        child = db.execute("SELECT * FROM users WHERE id=? AND is_admin=0", (child_id,)).fetchone()
        if not child:
            raise HTTPException(404)
        sessions = db.execute(
            """SELECT ts.*, COALESCE(wl.name, 'Mixed practice') AS list_name
               FROM test_sessions ts LEFT JOIN word_lists wl ON wl.id=ts.list_id
               WHERE ts.user_id=? ORDER BY ts.timestamp DESC LIMIT 20""",
            (child_id,),
        ).fetchall()
        badges = db.execute(
            "SELECT * FROM user_badges WHERE user_id=?", (child_id,)
        ).fetchall()
        unlocked = db.execute(
            """SELECT ul.list_id, ul.unlocked_at, wl.name FROM user_list_unlocks ul
               JOIN word_lists wl ON wl.id=ul.list_id WHERE ul.user_id=?""",
            (child_id,),
        ).fetchall()
        all_lists = db.execute("SELECT * FROM word_lists ORDER BY year_group, name").fetchall()
        word_stats = db.execute(
            """SELECT w.word,
                      COUNT(DISTINCT sa.session_id) AS sessions,
                      SUM(CASE WHEN sa.attempt_number=1 AND sa.correct=1 THEN 1 ELSE 0 END) AS first_try
               FROM words w
               JOIN spelling_attempts sa ON sa.word_id=w.id
               WHERE sa.user_id=?
               GROUP BY w.id ORDER BY w.word""",
            (child_id,),
        ).fetchall()
        unlocked_reward_files = unlocked_files(child_id, db)
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/child_detail.html", {
        "child": child, "sessions": sessions,
        "badges": badges, "unlocked": unlocked, "all_lists": all_lists,
        "word_stats": word_stats, "csrf_token": csrf,
        "reward_games": REWARD_GAMES, "unlocked_reward_files": unlocked_reward_files,
    })


@router.get("/children/{child_id}/edit")
def edit_child_form(child_id: int, request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        child = db.execute("SELECT * FROM users WHERE id=? AND is_admin=0", (child_id,)).fetchone()
        if not child:
            raise HTTPException(404)
        lists = db.execute("SELECT * FROM word_lists ORDER BY year_group, name").fetchall()
        unlocked_ids = [
            r["list_id"] for r in
            db.execute("SELECT list_id FROM user_list_unlocks WHERE user_id=?", (child_id,)).fetchall()
        ]
    csrf = generate_csrf_token(request)
    return templates.TemplateResponse(request, "admin/edit_child.html", {
        "child": child, "lists": lists, "unlocked_ids": unlocked_ids, "csrf_token": csrf
    })


@router.post("/children/{child_id}/edit")
def edit_child(
    child_id: int,
    request: Request,
    name: str = Form(...),
    dob: str = Form(...),
    new_password: str = Form(""),
    unlock_lists: list[int] = Form(default=[]),
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        if new_password:
            ph = hash_password(new_password)
            db.execute(
                "UPDATE users SET name=?, dob=?, password_hash=? WHERE id=?",
                (name.strip(), dob, ph, child_id),
            )
        else:
            db.execute(
                "UPDATE users SET name=?, dob=? WHERE id=?",
                (name.strip(), dob, child_id),
            )
        db.execute("DELETE FROM user_list_unlocks WHERE user_id=?", (child_id,))
        for lid in unlock_lists:
            db.execute(
                "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
                (child_id, lid, now),
            )
    return RedirectResponse(f"/admin/children/{child_id}", status_code=303)


@router.post("/children/{child_id}/delete")
def delete_child(
    child_id: int,
    request: Request,
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id=? AND is_admin=0", (child_id,))
    return RedirectResponse("/admin/", status_code=303)


# ── Unlock list for child (quick action from child detail) ─────────────────

@router.post("/children/{child_id}/unlock")
def unlock_list(
    child_id: int,
    request: Request,
    list_id: int = Form(...),
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
            (child_id, list_id, now),
        )
    return RedirectResponse(f"/admin/children/{child_id}", status_code=303)


# ── Reward game unlock/re-lock for child (admin override) ──────────────────

@router.post("/children/{child_id}/games/{filename}/toggle")
def toggle_game_unlock(
    child_id: int,
    filename: str,
    request: Request,
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    if filename not in {g["file"] for g in REWARD_GAMES}:
        raise HTTPException(404)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        already = db.execute(
            "SELECT 1 FROM user_game_unlocks WHERE user_id=? AND game_file=?",
            (child_id, filename),
        ).fetchone()
        if already:
            db.execute(
                "DELETE FROM user_game_unlocks WHERE user_id=? AND game_file=?",
                (child_id, filename),
            )
        else:
            db.execute(
                """INSERT OR IGNORE INTO user_game_unlocks
                   (user_id, game_file, earned_at, source) VALUES (?,?,?,?)""",
                (child_id, filename, now, "admin"),
            )
    return RedirectResponse(f"/admin/children/{child_id}", status_code=303)


# ── Audio cache warm ───────────────────────────────────────────────────────

@router.post("/warm-audio-cache")
def warm_audio_cache(
    request: Request,
    csrf_token: str = Form(...),
    admin=Depends(require_admin),
):
    verify_csrf_token(request, csrf_token)
    from services.tts import get_audio_url
    with get_db() as db:
        words = db.execute("SELECT DISTINCT word FROM words").fetchall()
    warmed = 0
    for row in words:
        with get_db() as db:
            url = get_audio_url(row["word"], db)
            if url:
                warmed += 1
    return RedirectResponse(f"/admin/?warmed={warmed}", status_code=303)

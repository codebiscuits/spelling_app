from fastapi import APIRouter, Request, Depends

from database import get_db
from auth import require_child
from templates_env import templates

router = APIRouter(prefix="/child")


@router.get("/dashboard")
def child_dashboard(request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        unlocked = db.execute(
            """SELECT wl.*, ul.unlocked_at
               FROM user_list_unlocks ul JOIN word_lists wl ON wl.id=ul.list_id
               WHERE ul.user_id=? ORDER BY wl.year_group, wl.name""",
            (user_id,),
        ).fetchall()
        badges = db.execute(
            "SELECT * FROM user_badges WHERE user_id=?", (user_id,)
        ).fetchall()
        recent_sessions = db.execute(
            """SELECT ts.*, wl.name AS list_name
               FROM test_sessions ts JOIN word_lists wl ON wl.id=ts.list_id
               WHERE ts.user_id=? ORDER BY ts.timestamp DESC LIMIT 5""",
            (user_id,),
        ).fetchall()
        child = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    badge_list_ids = {b["list_id"] for b in badges if b["badge_type"] == "badge"}
    trophy_list_ids = {b["list_id"] for b in badges if b["badge_type"] == "trophy"}
    return templates.TemplateResponse(request, "child/dashboard.html", {
        "child": child,
        "unlocked": unlocked,
        "badge_list_ids": badge_list_ids,
        "trophy_list_ids": trophy_list_ids,
        "recent_sessions": recent_sessions,
    })


@router.get("/pick-list")
def pick_list(request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        unlocked = db.execute(
            """SELECT wl.*, ul.unlocked_at
               FROM user_list_unlocks ul JOIN word_lists wl ON wl.id=ul.list_id
               WHERE ul.user_id=? ORDER BY wl.year_group, wl.name""",
            (user_id,),
        ).fetchall()
        badges = db.execute(
            "SELECT * FROM user_badges WHERE user_id=?", (user_id,)
        ).fetchall()
    badge_list_ids = {b["list_id"] for b in badges if b["badge_type"] == "badge"}
    trophy_list_ids = {b["list_id"] for b in badges if b["badge_type"] == "trophy"}
    return templates.TemplateResponse(request, "child/pick_list.html", {
        "unlocked": unlocked,
        "badge_list_ids": badge_list_ids,
        "trophy_list_ids": trophy_list_ids,
    })

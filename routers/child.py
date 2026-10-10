from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse

from database import get_db
from auth import require_child, verify_csrf_token
from services.arithmetic_facts import FACTORS
from services.gamification import award_skipped_list_trophies, london_date
from services.game_rewards import unlocked_files, next_locked, badges_until_next
from services.game_activity import (
    consume_game_credit,
    create_game_launch,
    record_game_play,
)
from templates_env import templates, MINI_GAMES, REWARD_GAMES

router = APIRouter(prefix="/child")


def _cabinet_slot(label: str, earned_at: str | None, name: str) -> dict:
    """One trophy in the cabinet. title is the accessible name, for example
    '7 times table: won on 12 Oct' or 'Year 3-4: not won yet'."""
    if earned_at:
        try:
            day = london_date(earned_at)
            date_text = f"{day.day} {day:%b}"
        except ValueError:
            date_text = earned_at[:10]
        title = f"{name}: won on {date_text}"
    else:
        title = f"{name}: not won yet"
    return {"label": label, "won": bool(earned_at), "title": title}


@router.get("/dashboard")
def child_dashboard(request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        unlocked = db.execute(
            """SELECT wl.*, ul.unlocked_at
               FROM user_list_unlocks ul JOIN word_lists wl ON wl.id=ul.list_id
               WHERE ul.user_id=? ORDER BY wl.position, wl.id""",
            (user_id,),
        ).fetchall()
        child = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        recent_sessions = db.execute(
            """SELECT ts.*, COALESCE(wl.name,
                      CASE ts.subject WHEN 'arithmetic' THEN 'Times tables' ELSE 'Mixed practice' END
                      ) AS list_name
               FROM test_sessions ts LEFT JOIN word_lists wl ON wl.id=ts.list_id
               WHERE ts.user_id=? ORDER BY ts.timestamp DESC LIMIT 5""",
            (user_id,),
        ).fetchall()
        badge_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM test_badges WHERE user_id=?", (user_id,)
        ).fetchone()["cnt"]
        medals = db.execute(
            """SELECT threshold FROM milestone_medals
               WHERE user_id=? AND subject='spelling' ORDER BY threshold""",
            (user_id,),
        ).fetchall()
        arithmetic_medals = db.execute(
            """SELECT threshold FROM milestone_medals
               WHERE user_id=? AND subject='arithmetic' ORDER BY threshold""",
            (user_id,),
        ).fetchall()
        # The trophy cabinet: every slot, won or not. Lists in curriculum order.
        # Lists before the child's first list count as won (practised at school).
        award_skipped_list_trophies(user_id, db)
        won = {
            (r["subject"], r["group_key"]): r["earned_at"] for r in db.execute(
                "SELECT subject, group_key, earned_at FROM mastery_trophies WHERE user_id=?",
                (user_id,),
            ).fetchall()
        }
        all_lists = db.execute("SELECT id, name FROM word_lists ORDER BY position, id").fetchall()
        cabinet_tables = [
            _cabinet_slot(str(t), won.get(("arithmetic", str(t))), f"{t} times table")
            for t in FACTORS
        ]
        cabinet_lists = [
            _cabinet_slot(lst["name"], won.get(("spelling", str(lst["id"]))), lst["name"])
            for lst in all_lists
        ]

        # Supportive per-list count: how many of its words the child has tried.
        # Deliberately no mastered/weak/stale split on the child's page.
        progress = {}
        for lst in unlocked:
            total = db.execute(
                "SELECT COUNT(*) AS cnt FROM words WHERE list_id=?", (lst["id"],)
            ).fetchone()["cnt"]
            practised = db.execute(
                """SELECT COUNT(DISTINCT sa.word_id) AS cnt
                   FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
                   WHERE sa.user_id=? AND w.list_id=? AND sa.attempt_number=1""",
                (user_id, lst["id"]),
            ).fetchone()["cnt"]
            progress[lst["id"]] = {"total": total, "practised": practised}

    with get_db() as db:
        unlocked_reward_files = unlocked_files(user_id, db)
        my_games = [g for g in REWARD_GAMES if g["file"] in unlocked_reward_files]
        locked = next_locked(user_id, db)
        mystery = {"hint": badges_until_next(user_id, db)} if locked else None

    return templates.TemplateResponse(request, "child/dashboard.html", {
        "child": child,
        "unlocked": unlocked,
        "recent_sessions": recent_sessions,
        "progress": progress,
        "badge_count": badge_count,
        "medals": medals,
        "arithmetic_medals": arithmetic_medals,
        "cabinet_tables": cabinet_tables,
        "cabinet_lists": cabinet_lists,
        "my_games": my_games,
        "mystery": mystery,
        "discovered_count": len(my_games),
    })



GAME_FILES = {g["file"] for g in MINI_GAMES}


def play_duration(score: int) -> int:
    """Seconds of play time earned by a test score: 60s at 10/20, +6s per
    extra point, capped at 120s for a perfect 20."""
    return max(60, (min(score, 20) - 10) * 6 + 60)


@router.post("/games/{filename}")
def play_game(
    filename: str,
    request: Request,
    csrf_token: str = Form(...),
    user=Depends(require_child),
):
    verify_csrf_token(request, csrf_token)
    if filename not in GAME_FILES:
        raise HTTPException(404)
    game = next(g for g in MINI_GAMES if g["file"] == filename)
    # One play per completed test: the results flow stores a single credit
    # server-side, then this route consumes it atomically with the play record.
    with get_db() as db:
        if game["tier"] == "reward" and filename not in unlocked_files(user["user_id"], db):
            raise HTTPException(404)
        score = consume_game_credit(user["user_id"], db)
        if score is None:
            return RedirectResponse("/child/dashboard", status_code=303)
        record_game_play(user["user_id"], filename, db)
        launch = create_game_launch(user["user_id"], filename, db)
    return templates.TemplateResponse(request, "child/game.html", {
        "game": game,
        "launch": launch,
        "duration": play_duration(score),
    })

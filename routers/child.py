from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse

from database import get_db
from auth import require_child
from services.arithmetic_facts import rung_name
from services.game_rewards import unlocked_files, next_locked, badges_until_next
from templates_env import templates, MINI_GAMES, REWARD_GAMES

router = APIRouter(prefix="/child")


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
        trophies = db.execute(
            """SELECT st.group_id AS list_id, wl.name AS list_name FROM start_trophies st
               JOIN word_lists wl ON wl.id=st.group_id
               WHERE st.user_id=? AND st.subject='spelling'
               ORDER BY wl.position, wl.id""",
            (user_id,),
        ).fetchall()

        arithmetic_medals = db.execute(
            """SELECT threshold FROM milestone_medals
               WHERE user_id=? AND subject='arithmetic' ORDER BY threshold""",
            (user_id,),
        ).fetchall()
        arithmetic_trophies = [
            {"name": rung_name(t["group_id"])} for t in db.execute(
                """SELECT group_id FROM start_trophies
                   WHERE user_id=? AND subject='arithmetic' ORDER BY group_id""",
                (user_id,),
            ).fetchall()
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

    trophy_list_ids = {t["list_id"] for t in trophies}

    with get_db() as db:
        unlocked_reward_files = unlocked_files(user_id, db)
        my_games = [g for g in REWARD_GAMES if g["file"] in unlocked_reward_files]
        locked = next_locked(user_id, db)
        mystery = {"hint": badges_until_next(user_id, db)} if locked else None

    return templates.TemplateResponse(request, "child/dashboard.html", {
        "child": child,
        "unlocked": unlocked,
        "trophy_list_ids": trophy_list_ids,
        "recent_sessions": recent_sessions,
        "progress": progress,
        "badge_count": badge_count,
        "medals": medals,
        "trophies": trophies,
        "arithmetic_medals": arithmetic_medals,
        "arithmetic_trophies": arithmetic_trophies,
        "my_games": my_games,
        "mystery": mystery,
        "discovered_count": len(my_games),
    })



GAME_FILES = {g["file"] for g in MINI_GAMES}


def play_duration(score: int) -> int:
    """Seconds of play time earned by a test score: 60s at 10/20, +6s per
    extra point, capped at 120s for a perfect 20."""
    return max(60, (min(score, 20) - 10) * 6 + 60)


@router.get("/games/{filename}")
def play_game(filename: str, request: Request, user=Depends(require_child)):
    if filename not in GAME_FILES:
        raise HTTPException(404)
    game = next(g for g in MINI_GAMES if g["file"] == filename)
    if game["tier"] == "reward":
        with get_db() as db:
            if filename not in unlocked_files(user["user_id"], db):
                raise HTTPException(404)
    # One play per completed test: the results flow banks a single game
    # credit (with the real session score); playing spends it.
    credit = request.session.pop("game_credit", None)
    if credit is None:
        return RedirectResponse("/child/dashboard", status_code=303)
    return templates.TemplateResponse(request, "child/game.html", {
        "game": game,
        "duration": play_duration(credit["score"]),
    })

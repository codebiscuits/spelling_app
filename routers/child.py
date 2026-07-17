from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse

from database import get_db
from auth import require_child
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
               WHERE ul.user_id=? ORDER BY wl.year_group, wl.name""",
            (user_id,),
        ).fetchall()
        badges = db.execute(
            "SELECT * FROM user_badges WHERE user_id=?", (user_id,)
        ).fetchall()
        recent_sessions = db.execute(
            """SELECT ts.*, COALESCE(wl.name, 'Mixed practice') AS list_name
               FROM test_sessions ts LEFT JOIN word_lists wl ON wl.id=ts.list_id
               WHERE ts.user_id=? ORDER BY ts.timestamp DESC LIMIT 5""",
            (user_id,),
        ).fetchall()
        child = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

        badge_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM test_badges WHERE user_id=?", (user_id,)
        ).fetchone()["cnt"]
        medals = db.execute(
            """SELECT ub.list_id, wl.name AS list_name FROM user_badges ub
               JOIN word_lists wl ON wl.id=ub.list_id
               WHERE ub.user_id=? AND ub.badge_type='medal' ORDER BY wl.year_group, wl.name""",
            (user_id,),
        ).fetchall()
        trophies = db.execute(
            """SELECT ub.list_id, wl.name AS list_name FROM user_badges ub
               JOIN word_lists wl ON wl.id=ub.list_id
               WHERE ub.user_id=? AND ub.badge_type='trophy' ORDER BY wl.year_group, wl.name""",
            (user_id,),
        ).fetchall()

        # Per-list mastery progress
        progress = {}
        for lst in unlocked:
            lid = lst["id"]
            total = db.execute(
                "SELECT COUNT(*) AS cnt FROM words WHERE list_id=?", (lid,)
            ).fetchone()["cnt"]
            first_try = db.execute(
                """SELECT COUNT(DISTINCT sa.word_id) AS cnt
                   FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
                   WHERE sa.user_id=? AND w.list_id=? AND sa.attempt_number=1 AND sa.correct=1""",
                (user_id, lid),
            ).fetchone()["cnt"]
            second_try = db.execute(
                """SELECT COUNT(DISTINCT sa.word_id) AS cnt
                   FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
                   WHERE sa.user_id=? AND w.list_id=? AND sa.attempt_number=2 AND sa.correct=1
                     AND sa.word_id NOT IN (
                       SELECT word_id FROM spelling_attempts
                       WHERE user_id=? AND attempt_number=1 AND correct=1
                     )""",
                (user_id, lid, user_id),
            ).fetchone()["cnt"]
            attempted = db.execute(
                """SELECT COUNT(DISTINCT sa.word_id) AS cnt
                   FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
                   WHERE sa.user_id=? AND w.list_id=?""",
                (user_id, lid),
            ).fetchone()["cnt"]
            progress[lid] = {
                "total": total,
                "first_try": first_try,
                "second_try": second_try,
                "first_pct": round(first_try / total * 100) if total else 0,
                "second_pct": round(second_try / total * 100) if total else 0,
                "practising": attempted - first_try,
                "new": total - attempted,
            }

    medal_list_ids = {b["list_id"] for b in badges if b["badge_type"] == "medal"}
    trophy_list_ids = {b["list_id"] for b in badges if b["badge_type"] == "trophy"}

    with get_db() as db:
        unlocked_reward_files = unlocked_files(user_id, db)
        my_games = [g for g in REWARD_GAMES if g["file"] in unlocked_reward_files]
        locked = next_locked(user_id, db)
        mystery = {"hint": badges_until_next(user_id, db)} if locked else None

    return templates.TemplateResponse(request, "child/dashboard.html", {
        "child": child,
        "unlocked": unlocked,
        "medal_list_ids": medal_list_ids,
        "trophy_list_ids": trophy_list_ids,
        "recent_sessions": recent_sessions,
        "progress": progress,
        "badge_count": badge_count,
        "medals": medals,
        "trophies": trophies,
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

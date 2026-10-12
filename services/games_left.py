"""Forecast when each child will unlock their last reward game.

A child unlocks the next reward game on every BADGE_STEP-th badge
(services/game_rewards.py). So the badges a child still needs, divided by
their recent badge pace, gives a run-out date. The admin dashboard shows it,
and scripts/games_left_alert.py uses it to warn Ross in time to make more.

Read-only: nothing here writes to the database.
"""
import math
from datetime import date, datetime, timedelta, timezone

from services.game_rewards import BADGE_STEP
from templates_env import REWARD_GAMES

PACE_WINDOW_DAYS = 28
LEAD_DAYS = 7


def _day(iso: str) -> date:
    return datetime.fromisoformat(iso).astimezone(timezone.utc).date()


def child_forecast(user, db, today: date | None = None,
                   window_days: int = PACE_WINDOW_DAYS, lead_days: int = LEAD_DAYS) -> dict:
    """Games left, badge pace and run-out date for one child.

    `alert` is True when the child has earned a badge inside the pace window
    (so an idle or test account never alerts) and either has no games left or
    is forecast to run out within `lead_days`.
    """
    today = today or datetime.now(timezone.utc).date()
    reward_files = {g["file"] for g in REWARD_GAMES}
    unlocked = {
        r["game_file"] for r in db.execute(
            "SELECT game_file FROM user_game_unlocks WHERE user_id=?", (user["id"],)
        ).fetchall()
    } & reward_files
    games_left = len(reward_files) - len(unlocked)

    stamps = [r["earned_at"] for r in db.execute(
        "SELECT earned_at FROM test_badges WHERE user_id=?", (user["id"],)
    ).fetchall()]
    badges = len(stamps)
    since = today - timedelta(days=window_days)
    recent = sum(1 for s in stamps if _day(s) > since)
    pace_per_week = recent / window_days * 7

    # The next unlock comes at the next multiple of BADGE_STEP, then one game
    # every BADGE_STEP badges after that.
    to_next = BADGE_STEP - (badges % BADGE_STEP)
    badges_needed = 0 if games_left == 0 else (games_left - 1) * BADGE_STEP + to_next

    if games_left == 0:
        run_out = today
    elif recent:
        run_out = today + timedelta(days=math.ceil(badges_needed / (recent / window_days)))
    else:
        run_out = None

    active = recent > 0
    alert = active and run_out is not None and run_out <= today + timedelta(days=lead_days)
    return {
        "user_id": user["id"], "name": user["name"],
        "games_total": len(reward_files), "games_left": games_left,
        "badges": badges, "recent_badges": recent, "pace_per_week": round(pace_per_week, 1),
        "badges_needed": badges_needed, "run_out": run_out, "active": active, "alert": alert,
    }


def all_forecasts(db, today: date | None = None, **kw) -> list[dict]:
    """One forecast per child (non-admin user), earliest run-out first."""
    children = db.execute("SELECT id, name FROM users WHERE is_admin=0 ORDER BY name").fetchall()
    rows = [child_forecast(c, db, today, **kw) for c in children]
    return sorted(rows, key=lambda r: (r["run_out"] is None, r["run_out"] or date.max, r["name"]))

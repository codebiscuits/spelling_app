from datetime import datetime, timezone

from templates_env import REWARD_GAMES

BADGE_STEP = 3


def unlocked_files(user_id: int, db) -> set[str]:
    """Reward-tier game files this user has unlocked."""
    rows = db.execute(
        "SELECT game_file FROM user_game_unlocks WHERE user_id=?", (user_id,)
    ).fetchall()
    return {r["game_file"] for r in rows}


def next_locked(user_id: int, db) -> dict | None:
    """Next reward game entry (lowest release_order) not yet unlocked, or None."""
    unlocked = unlocked_files(user_id, db)
    for game in REWARD_GAMES:
        if game["file"] not in unlocked:
            return game
    return None


def badges_until_next(user_id: int, db) -> int:
    """Badges needed to reach the next multiple of BADGE_STEP (1..3)."""
    count = db.execute(
        "SELECT COUNT(*) AS cnt FROM test_badges WHERE user_id=?", (user_id,)
    ).fetchone()["cnt"]
    remainder = count % BADGE_STEP
    return BADGE_STEP - remainder if remainder else BADGE_STEP


def check_and_unlock(user_id: int, award: dict, db) -> dict | None:
    """Apply the §1.3 earning ladder given the session's aggregated award
    dict (badge from gamification.award_session_badge(), medal/trophy
    aggregated across the per-list gamification.check_and_award() calls).

    Trigger order: trophy this session -> medal this session -> badge this
    session AND lifetime badge count is a multiple of BADGE_STEP. At most
    one unlock is applied (a trophy+medal session still yields one).

    Returns the newly-unlocked MINI_GAMES entry, or None.
    """
    if award.get("trophy_awarded"):
        source = "trophy"
    elif award.get("medal_awarded"):
        source = "medal"
    elif award.get("badge_awarded"):
        badge_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM test_badges WHERE user_id=?", (user_id,)
        ).fetchone()["cnt"]
        source = "badge" if badge_count and badge_count % BADGE_STEP == 0 else None
    else:
        source = None

    if source is None:
        return None

    game = next_locked(user_id, db)
    if game is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT OR IGNORE INTO user_game_unlocks
           (user_id, game_file, earned_at, source) VALUES (?,?,?,?)""",
        (user_id, game["file"], now, source),
    )
    return game

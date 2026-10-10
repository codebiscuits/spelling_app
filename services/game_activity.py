import secrets
from datetime import datetime, timedelta, timezone


RECENT_PLAY_WINDOW = timedelta(days=30)
GAME_LAUNCH_LIFETIME = timedelta(minutes=5)


def recently_played_files(user_id: int, db, now: datetime | None = None) -> set[str]:
    """Return game files this child played during the last 30 days."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)
    cutoff = current_time - RECENT_PLAY_WINDOW
    rows = db.execute(
        """SELECT DISTINCT game_file FROM user_game_plays
           WHERE user_id=? AND played_at>=?""",
        (user_id, cutoff.isoformat()),
    ).fetchall()
    return {row["game_file"] for row in rows}


def record_game_play(user_id: int, game_file: str, db) -> None:
    """Record a child starting an earned mini-game play."""
    db.execute(
        """INSERT INTO user_game_plays (user_id, game_file, played_at)
           VALUES (?,?,?)""",
        (user_id, game_file, datetime.now(timezone.utc).isoformat()),
    )


def create_game_launch(user_id: int, game_file: str, db) -> str:
    """Create a short-lived, single-use capability for a game's iframe."""
    now = datetime.now(timezone.utc)
    nonce = secrets.token_urlsafe(32)
    db.execute("DELETE FROM user_game_launches WHERE expires_at<?", (now.isoformat(),))
    db.execute(
        """INSERT INTO user_game_launches (nonce, user_id, game_file, expires_at)
           VALUES (?,?,?,?)""",
        (nonce, user_id, game_file, (now + GAME_LAUNCH_LIFETIME).isoformat()),
    )
    return nonce


def consume_game_launch(user_id: int, game_file: str, nonce: str, db) -> bool:
    """Atomically consume a valid iframe launch capability."""
    deleted = db.execute(
        """DELETE FROM user_game_launches
           WHERE nonce=? AND user_id=? AND game_file=? AND expires_at>=?""",
        (nonce, user_id, game_file, datetime.now(timezone.utc).isoformat()),
    )
    return deleted.rowcount == 1


def grant_game_credit(user_id: int, session_id: int, score: int, db) -> None:
    """Persist one game credit per qualifying completed spelling session."""
    db.execute(
        """INSERT OR IGNORE INTO user_game_credits
           (session_id, user_id, score, status, earned_at) VALUES (?,?,?,?,?)""",
        (session_id, user_id, score, "available", datetime.now(timezone.utc).isoformat()),
    )


def consume_game_credit(user_id: int, db) -> int | None:
    """Atomically mark the child's oldest available game credit as consumed."""
    row = db.execute(
        """UPDATE user_game_credits SET status='consumed'
           WHERE id=(
               SELECT id FROM user_game_credits
               WHERE user_id=? AND status='available' ORDER BY id LIMIT 1
           )
           RETURNING score""",
        (user_id,),
    ).fetchone()
    return row["score"] if row else None


def forfeit_game_credits(user_id: int, db) -> None:
    """Mark unspent credits as forfeited after a non-qualifying later test."""
    db.execute(
        "UPDATE user_game_credits SET status='forfeited' WHERE user_id=? AND status='available'",
        (user_id,),
    )


QUALIFYING_SCORE = 10  # When adjusting this threshold, update README.md and SETUP.md as well


def offer_games(user_id: int, session_id: int, score: int, db) -> dict:
    """Settle the game credit for a finished practice of either subject and
    choose the games to offer. A qualifying score banks one credit; a lower
    score forfeits any unspent one. Games played in the last 30 days come
    first; the rest sit under All games."""
    from templates_env import CLASSIC_GAMES, REWARD_GAMES
    from services.game_rewards import badges_until_next, next_locked, unlocked_files

    offer = {"recent_games": [], "older_games": [], "mystery": None}
    if score < QUALIFYING_SCORE:
        forfeit_game_credits(user_id, db)
        return offer
    grant_game_credit(user_id, session_id, score, db)
    unlocked = unlocked_files(user_id, db)
    available = CLASSIC_GAMES + [g for g in REWARD_GAMES if g["file"] in unlocked]
    recent = recently_played_files(user_id, db)
    offer["recent_games"] = [g for g in available if g["file"] in recent]
    offer["older_games"] = [g for g in available if g["file"] not in recent]
    if next_locked(user_id, db):
        offer["mystery"] = {"hint": badges_until_next(user_id, db)}
    return offer

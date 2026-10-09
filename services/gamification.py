"""Badges, medals and trophies for spelling.

* Badge: final score >= 16/20, at most one per child per Europe/London
  calendar day. The first qualifying practice of the day earns it.
* Medal: one for each ten distinct words first mastered (a word counts
  once, ever). Backfilled medals are silent.
* Trophy: one per list, at the child's first ordinary first attempt at a
  word from that list. Backfilled trophies are silent.

Only every third badge unlocks a game (see game_rewards.py).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from services.spelling_progression import SUBJECT, load_history, mastered_word_ids

LONDON = ZoneInfo("Europe/London")
BADGE_SCORE = 16
MEDAL_STEP = 10


def london_date(when: datetime | str):
    if isinstance(when, str):
        when = datetime.fromisoformat(when)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(LONDON).date()


def award_session_badge(user_id: int, session_id: int, session_score: int, db,
                        now: datetime | None = None) -> bool:
    """Award today's badge if the score qualifies and none was earned yet
    on this London calendar day. Returns True when a badge was awarded."""
    if session_score < BADGE_SCORE:
        return False
    now = now or datetime.now(timezone.utc)
    today = london_date(now)
    # Badges are few per child; compare London dates in Python (SQL has no
    # time zone database).
    recent = db.execute(
        "SELECT earned_at, session_id FROM test_badges WHERE user_id=?", (user_id,)
    ).fetchall()
    for row in recent:
        if row["session_id"] == session_id or london_date(row["earned_at"]) == today:
            return False
    db.execute(
        "INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)",
        (user_id, session_id, now.astimezone(timezone.utc).isoformat()),
    )
    return True


def record_mastery_and_medals(user_id: int, db, now: datetime | None = None) -> list[int]:
    """Record newly mastered words as first-mastered, then award any medal
    thresholds reached. Returns the thresholds of the medals earned now."""
    now_s = (now or datetime.now(timezone.utc)).isoformat()
    hist = load_history(user_id, db)
    known = {
        r["item_key"] for r in db.execute(
            "SELECT item_key FROM first_mastered WHERE user_id=? AND subject=?",
            (user_id, SUBJECT),
        ).fetchall()
    }
    for wid in sorted(mastered_word_ids(hist)):
        if str(wid) not in known:
            db.execute(
                """INSERT OR IGNORE INTO first_mastered (user_id, subject, item_key, mastered_at)
                   VALUES (?,?,?,?)""",
                (user_id, SUBJECT, str(wid), now_s),
            )
    total = db.execute(
        "SELECT COUNT(*) AS c FROM first_mastered WHERE user_id=? AND subject=?",
        (user_id, SUBJECT),
    ).fetchone()["c"]
    earned = []
    for threshold in range(MEDAL_STEP, total + 1, MEDAL_STEP):
        cur = db.execute(
            """INSERT OR IGNORE INTO milestone_medals
               (user_id, subject, threshold, earned_at, silent) VALUES (?,?,?,?,0)""",
            (user_id, SUBJECT, threshold, now_s),
        )
        if cur.rowcount:
            earned.append(threshold)
    return earned


def award_start_trophies(user_id: int, db, now: datetime | None = None) -> list[str]:
    """Award a trophy for each list the child has started and has no trophy
    for yet. Returns the names of the lists awarded now."""
    now_s = (now or datetime.now(timezone.utc)).isoformat()
    rows = db.execute(
        """SELECT wl.id, wl.name, MIN(sa.id) AS first_attempt
           FROM spelling_attempts sa
           JOIN words w ON w.id=sa.word_id
           JOIN word_lists wl ON wl.id=w.list_id
           WHERE sa.user_id=? AND sa.attempt_number=1
             AND wl.id NOT IN (SELECT group_id FROM start_trophies
                               WHERE user_id=? AND subject=?)
           GROUP BY wl.id ORDER BY first_attempt""",
        (user_id, user_id, SUBJECT),
    ).fetchall()
    names = []
    for r in rows:
        db.execute(
            """INSERT OR IGNORE INTO start_trophies
               (user_id, subject, group_id, earned_at, silent) VALUES (?,?,?,?,0)""",
            (user_id, SUBJECT, r["id"], now_s),
        )
        names.append(r["name"])
    return names

"""Badges, medals and trophies for spelling and arithmetic.

* Badge: final score >= 16/20, at most one per child per Europe/London
  calendar day. The first qualifying practice of the day earns it.
* Medal: one for each ten distinct words first mastered (a word counts
  once, ever). Backfilled medals are silent.
* Start record: one per list, at the child's first ordinary first attempt at
  a word from that list (``start_trophies``). Shown only as a plain results
  message, never as a trophy. Backfilled records are silent.
* Trophy (mastery): one per word list, and one per times table 2 to 12
  (``mastery_trophies``), won when every item in the group has a
  ``first_mastered`` row. Permanent: a later slip or a word added to the
  list later never removes it.

A badge is one per child per London day across BOTH subjects: both read the
same test_badges table, and arithmetic sessions live in test_sessions too.
Arithmetic medals count distinct directions first secured; arithmetic
start records are one per ladder rung (group_id = rung number).

Only every third badge unlocks a game (see game_rewards.py).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from services import arithmetic_progression as arith
from services.arithmetic_facts import FACTORS, FACTS, LADDER, rung_name
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


def _record_medals(user_id: int, db, subject: str, mastered_keys: list[str],
                   now: datetime | None) -> list[int]:
    now_s = (now or datetime.now(timezone.utc)).isoformat()
    for key in mastered_keys:
        db.execute(
            """INSERT OR IGNORE INTO first_mastered (user_id, subject, item_key, mastered_at)
               VALUES (?,?,?,?)""",
            (user_id, subject, key, now_s),
        )
    total = db.execute(
        "SELECT COUNT(*) AS c FROM first_mastered WHERE user_id=? AND subject=?",
        (user_id, subject),
    ).fetchone()["c"]
    earned = []
    for threshold in range(MEDAL_STEP, total + 1, MEDAL_STEP):
        cur = db.execute(
            """INSERT OR IGNORE INTO milestone_medals
               (user_id, subject, threshold, earned_at, silent) VALUES (?,?,?,?,0)""",
            (user_id, subject, threshold, now_s),
        )
        if cur.rowcount:
            earned.append(threshold)
    return earned


def record_mastery_and_medals(user_id: int, db, now: datetime | None = None) -> list[int]:
    """Record newly mastered words as first-mastered, then award any medal
    thresholds reached. Returns the thresholds of the medals earned now."""
    mastered = sorted(mastered_word_ids(load_history(user_id, db)))
    return _record_medals(user_id, db, SUBJECT, [str(w) for w in mastered], now)


def record_arithmetic_mastery_and_medals(user_id: int, db, now: datetime | None = None) -> list[int]:
    """The same for arithmetic: a medal for each ten distinct directions
    first secured. A direction counts once, ever."""
    secure = sorted(arith.secure_keys(arith.load_history(user_id, db)))
    return _record_medals(user_id, db, arith.SUBJECT, secure, now)


def award_start_trophies(user_id: int, db, now: datetime | None = None) -> list[str]:
    """Record each list the child has started and has no start record for
    yet (``start_trophies``). Returns the names of the lists recorded now.
    The results page shows these as a plain message, not as a trophy."""
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


def award_arithmetic_trophies(user_id: int, db, now: datetime | None = None) -> list[str]:
    """Record each ladder rung the child has started (an ordinary first
    attempt at one of its directions, right or wrong) and has no start
    record for yet. Returns the names of the rungs recorded now."""
    now_s = (now or datetime.now(timezone.utc)).isoformat()
    have = {
        r["group_id"] for r in db.execute(
            "SELECT group_id FROM start_trophies WHERE user_id=? AND subject=?",
            (user_id, arith.SUBJECT),
        ).fetchall()
    }
    names = []
    for rung, _ in arith.started_rungs(user_id, db):
        if rung in have:
            continue
        db.execute(
            """INSERT OR IGNORE INTO start_trophies
               (user_id, subject, group_id, earned_at, silent) VALUES (?,?,?,?,0)""",
            (user_id, arith.SUBJECT, rung, now_s),
        )
        noun = "times tables" if len(LADDER[rung - 1]) > 1 else "times table"
        names.append(f"the {rung_name(rung)} {noun}")
    return names


# ── Mastery trophies ───────────────────────────────────────────────────────

def _mastered_keys(user_id: int, db, subject: str) -> set[str]:
    return {
        r["item_key"] for r in db.execute(
            "SELECT item_key FROM first_mastered WHERE user_id=? AND subject=?",
            (user_id, subject),
        ).fetchall()
    }


def table_fact_keys(table: int) -> list[str]:
    """Every direction that belongs to a times table: all x t and all / t
    facts (for division, t is the divisor or the quotient)."""
    return [k for k, f in FACTS.items() if table in f.factors]


def _insert_trophy(user_id: int, db, subject: str, group_key: str, now_s: str) -> bool:
    cur = db.execute(
        """INSERT OR IGNORE INTO mastery_trophies
           (user_id, subject, group_key, earned_at, silent) VALUES (?,?,?,?,0)""",
        (user_id, subject, group_key, now_s),
    )
    return bool(cur.rowcount)


def award_spelling_mastery_trophies(user_id: int, db, now: datetime | None = None) -> list[dict]:
    """Win a trophy for every word list whose words all have a
    ``first_mastered`` row. A list with no words never wins one. Checks all
    lists each time, so a child who already qualifies gets it at the next
    results page. Returns ``{"group_key", "label"}`` for each trophy won now."""
    now_s = (now or datetime.now(timezone.utc)).isoformat()
    mastered = _mastered_keys(user_id, db, SUBJECT)
    have = {
        r["group_key"] for r in db.execute(
            "SELECT group_key FROM mastery_trophies WHERE user_id=? AND subject=?",
            (user_id, SUBJECT),
        ).fetchall()
    }
    words_by_list: dict[int, list[str]] = {}
    for r in db.execute("SELECT id, list_id FROM words").fetchall():
        words_by_list.setdefault(r["list_id"], []).append(str(r["id"]))
    won = []
    for lst in db.execute("SELECT id, name FROM word_lists ORDER BY position, id").fetchall():
        key = str(lst["id"])
        words = words_by_list.get(lst["id"], [])
        if key in have or not words or not mastered.issuperset(words):
            continue
        if _insert_trophy(user_id, db, SUBJECT, key, now_s):
            won.append({"group_key": key, "label": lst["name"]})
    return won


def award_arithmetic_mastery_trophies(user_id: int, db, now: datetime | None = None) -> list[dict]:
    """Win a trophy for every times table 2 to 12 whose every direction
    (all x t and / t facts) has a ``first_mastered`` row. Returns
    ``{"group_key", "label"}`` for each trophy won now; label is the number."""
    now_s = (now or datetime.now(timezone.utc)).isoformat()
    mastered = _mastered_keys(user_id, db, arith.SUBJECT)
    have = {
        r["group_key"] for r in db.execute(
            "SELECT group_key FROM mastery_trophies WHERE user_id=? AND subject=?",
            (user_id, arith.SUBJECT),
        ).fetchall()
    }
    won = []
    for t in FACTORS:
        key = str(t)
        if key in have or not mastered.issuperset(table_fact_keys(t)):
            continue
        if _insert_trophy(user_id, db, arith.SUBJECT, key, now_s):
            won.append({"group_key": key, "label": str(t)})
    return won

import math
from datetime import datetime, timezone


def award_session_badge(user_id: int, session_id: int, session_score: int, db) -> bool:
    """Badge — scored >= 16/20 on this session (unlimited, but exactly one
    per session regardless of how many lists the session touched)."""
    if session_score < 16:
        return False
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)",
        (user_id, session_id, now),
    )
    return True


def check_and_award(user_id: int, list_id: int, db) -> dict:
    """
    Evaluate and award per-list medals and trophies.

    Medal  — >= 50% of list words spelled correctly first-try at least once (once per list)
    Trophy — next list unlocked: >= 95% first-try correct + all remaining second-try correct (once per list)
    """
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "medal_awarded": False,
        "trophy_awarded": False,
        "lists_unlocked": [],
    }

    existing_user_badges = {
        r["badge_type"]
        for r in db.execute(
            "SELECT badge_type FROM user_badges WHERE user_id=? AND list_id=?",
            (user_id, list_id),
        ).fetchall()
    }

    total_words = db.execute(
        "SELECT COUNT(*) AS cnt FROM words WHERE list_id=?", (list_id,)
    ).fetchone()["cnt"]

    if total_words == 0:
        return result

    first_try_ids = {
        r["word_id"]
        for r in db.execute(
            """SELECT DISTINCT sa.word_id
               FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
               WHERE sa.user_id=? AND w.list_id=? AND sa.attempt_number=1 AND sa.correct=1""",
            (user_id, list_id),
        ).fetchall()
    }

    # --- Medal: >= 50% of words first-try correct at least once ---
    if "medal" not in existing_user_badges:
        if len(first_try_ids) >= math.ceil(0.5 * total_words):
            db.execute(
                "INSERT OR IGNORE INTO user_badges (user_id, list_id, badge_type, earned_at) VALUES (?,?,?,?)",
                (user_id, list_id, "medal", now),
            )
            result["medal_awarded"] = True

    # --- Trophy + list unlock: >= 95% first-try, all remaining second-try ---
    if "trophy" not in existing_user_badges:
        threshold = math.ceil(0.95 * total_words)
        if len(first_try_ids) >= threshold:
            remaining_ids = {
                r["id"] for r in db.execute(
                    "SELECT id FROM words WHERE list_id=?", (list_id,)
                ).fetchall()
            } - first_try_ids

            all_remaining_second_try = all(
                db.execute(
                    """SELECT 1 FROM spelling_attempts
                       WHERE user_id=? AND word_id=? AND attempt_number=2 AND correct=1 LIMIT 1""",
                    (user_id, wid),
                ).fetchone()
                for wid in remaining_ids
            )

            if all_remaining_second_try:
                db.execute(
                    "INSERT OR IGNORE INTO user_badges (user_id, list_id, badge_type, earned_at) VALUES (?,?,?,?)",
                    (user_id, list_id, "trophy", now),
                )
                result["trophy_awarded"] = True

                list_row = db.execute(
                    "SELECT year_group FROM word_lists WHERE id=?", (list_id,)
                ).fetchone()
                if list_row and list_row["year_group"]:
                    current_yg = list_row["year_group"]
                    next_yg = current_yg + 2 if current_yg in (1, 3) else current_yg + 1
                    for nl in db.execute(
                        "SELECT id FROM word_lists WHERE year_group=?", (next_yg,)
                    ).fetchall():
                        cur = db.execute(
                            "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
                            (user_id, nl["id"], now),
                        )
                        if cur.rowcount:
                            result["lists_unlocked"].append(nl["id"])

    return result

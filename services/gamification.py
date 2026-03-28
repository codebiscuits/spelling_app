import math
from datetime import datetime, timezone


def check_and_award(user_id: int, list_id: int, db) -> dict:
    """
    Evaluate badge/trophy/unlock conditions and award if met.

    Unlock condition: >=95% of words in the list spelled correctly on first attempt
    (across all sessions, ever), AND all remaining words spelled correctly on second
    attempt at least once.

    Badge: avg score across all word/session pairs >= 1.4 (separate milestone).
    Trophy: every word spelled correctly first-try at least once.
    """
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "badge_awarded": False,
        "trophy_awarded": False,
        "lists_unlocked": [],
    }

    existing = {
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

    # Words the child has spelled correctly on first attempt (at least once, ever)
    first_try_ids = {
        r["word_id"]
        for r in db.execute(
            """SELECT DISTINCT sa.word_id
               FROM spelling_attempts sa
               JOIN words w ON w.id = sa.word_id
               WHERE sa.user_id=? AND w.list_id=? AND sa.attempt_number=1 AND sa.correct=1""",
            (user_id, list_id),
        ).fetchall()
    }

    # --- Badge: avg score >= 1.4 ---
    if "badge" not in existing:
        score_rows = db.execute(
            """SELECT MAX(CASE WHEN attempt_number=1 AND correct=1 THEN 2
                              WHEN attempt_number=2 AND correct=1 THEN 1
                              ELSE 0 END) AS word_score
               FROM spelling_attempts sa
               JOIN words w ON w.id=sa.word_id
               WHERE sa.user_id=? AND w.list_id=?
               GROUP BY sa.session_id, sa.word_id""",
            (user_id, list_id),
        ).fetchall()
        if score_rows:
            avg = sum(r["word_score"] for r in score_rows) / len(score_rows)
            if avg >= 1.4:
                db.execute(
                    "INSERT OR IGNORE INTO user_badges (user_id, list_id, badge_type, earned_at) VALUES (?,?,?,?)",
                    (user_id, list_id, "badge", now),
                )
                result["badge_awarded"] = True

    # --- Trophy: every word spelled correctly first-try at least once ---
    if "trophy" not in existing and len(first_try_ids) >= total_words:
        db.execute(
            "INSERT OR IGNORE INTO user_badges (user_id, list_id, badge_type, earned_at) VALUES (?,?,?,?)",
            (user_id, list_id, "trophy", now),
        )
        result["trophy_awarded"] = True

    # --- List unlock: >=95% first-try correct, all remaining second-try correct ---
    already_unlocked_next = db.execute(
        """SELECT COUNT(*) AS cnt FROM user_list_unlocks ul
           JOIN word_lists wl ON wl.id = ul.list_id
           JOIN word_lists cur ON cur.id = ?
           WHERE ul.user_id=? AND wl.year_group > cur.year_group""",
        (list_id, user_id),
    ).fetchone()["cnt"]

    if already_unlocked_next == 0:
        threshold = math.ceil(0.95 * total_words)
        if len(first_try_ids) >= threshold:
            # Check all remaining words have been spelled correctly on attempt 2
            remaining_ids = set(
                r["id"] for r in db.execute(
                    "SELECT id FROM words WHERE list_id=?", (list_id,)
                ).fetchall()
            ) - first_try_ids

            second_try_ok = True
            for wid in remaining_ids:
                ever_second = db.execute(
                    """SELECT 1 FROM spelling_attempts
                       WHERE user_id=? AND word_id=? AND attempt_number=2 AND correct=1
                       LIMIT 1""",
                    (user_id, wid),
                ).fetchone()
                if not ever_second:
                    second_try_ok = False
                    break

            if second_try_ok:
                list_row = db.execute(
                    "SELECT year_group FROM word_lists WHERE id=?", (list_id,)
                ).fetchone()
                if list_row and list_row["year_group"]:
                    current_yg = list_row["year_group"]
                    next_yg = current_yg + 2 if current_yg in (1, 3) else current_yg + 1
                    next_lists = db.execute(
                        "SELECT id FROM word_lists WHERE year_group=?", (next_yg,)
                    ).fetchall()
                    for nl in next_lists:
                        db.execute(
                            "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
                            (user_id, nl["id"], now),
                        )
                        result["lists_unlocked"].append(nl["id"])

    return result

from datetime import datetime, timezone


def check_and_award(user_id: int, list_id: int, db) -> dict:
    """
    Evaluate badge/trophy conditions and award if met.
    Returns a dict describing what was awarded.
    """
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "badge_awarded": False,
        "trophy_awarded": False,
        "badge_already_had": False,
        "lists_unlocked": [],
    }

    # --- Check existing badges ---
    existing = {
        r["badge_type"]
        for r in db.execute(
            "SELECT badge_type FROM user_badges WHERE user_id=? AND list_id=?",
            (user_id, list_id),
        ).fetchall()
    }
    result["badge_already_had"] = "badge" in existing

    # --- Badge: avg score across all word/session pairs ≥ 1.4 ---
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

                # Unlock next list
                list_row = db.execute(
                    "SELECT year_group FROM word_lists WHERE id=?", (list_id,)
                ).fetchone()
                if list_row and list_row["year_group"]:
                    current_yg = list_row["year_group"]
                    # UK curriculum pairs: 1→3, 3→5, others +1
                    if current_yg in (1, 3):
                        next_yg = current_yg + 2
                    else:
                        next_yg = current_yg + 1
                    next_lists = db.execute(
                        "SELECT id FROM word_lists WHERE year_group=?", (next_yg,)
                    ).fetchall()
                    for nl in next_lists:
                        db.execute(
                            "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
                            (user_id, nl["id"], now),
                        )
                        result["lists_unlocked"].append(nl["id"])

    # --- Trophy: every word has at least one first-attempt correct ---
    if "trophy" not in existing:
        total_words = db.execute(
            "SELECT COUNT(*) AS cnt FROM words WHERE list_id=?", (list_id,)
        ).fetchone()["cnt"]
        mastered = db.execute(
            """SELECT COUNT(DISTINCT w.id) AS cnt
               FROM words w
               JOIN spelling_attempts sa ON sa.word_id=w.id
               WHERE w.list_id=? AND sa.user_id=? AND sa.attempt_number=1 AND sa.correct=1""",
            (list_id, user_id),
        ).fetchone()["cnt"]
        if total_words > 0 and mastered >= total_words:
            db.execute(
                "INSERT OR IGNORE INTO user_badges (user_id, list_id, badge_type, earned_at) VALUES (?,?,?,?)",
                (user_id, list_id, "trophy", now),
            )
            result["trophy_awarded"] = True

    return result

"""One-time backfill for the release 2 migration.

Writes only into the new tables. It derives each child's current mastery
from spelling_attempts, records those words as first-mastered, and awards
the medals and start trophies already reached with silent=1, so release
day shows no banners and unlocks no games.
"""
from services.spelling_progression import SUBJECT, load_history, mastered_word_ids

MEDAL_STEP = 10


def backfill_awards(con, now: str) -> None:
    users = con.execute(
        """SELECT DISTINCT user_id FROM spelling_attempts WHERE attempt_number<3"""
    ).fetchall()
    for u in users:
        uid = u["user_id"]
        hist = load_history(uid, con)
        mastered = mastered_word_ids(hist)
        for wid in sorted(mastered):
            con.execute(
                """INSERT OR IGNORE INTO first_mastered
                   (user_id, subject, item_key, mastered_at) VALUES (?,?,?,?)""",
                (uid, SUBJECT, str(wid), now),
            )
        total = con.execute(
            "SELECT COUNT(*) FROM first_mastered WHERE user_id=? AND subject=?", (uid, SUBJECT)
        ).fetchone()[0]
        for threshold in range(MEDAL_STEP, total + 1, MEDAL_STEP):
            con.execute(
                """INSERT OR IGNORE INTO milestone_medals
                   (user_id, subject, threshold, earned_at, silent) VALUES (?,?,?,?,1)""",
                (uid, SUBJECT, threshold, now),
            )
        lists = con.execute(
            """SELECT DISTINCT w.list_id FROM spelling_attempts sa
               JOIN words w ON w.id=sa.word_id
               WHERE sa.user_id=? AND sa.attempt_number<3""",
            (uid,),
        ).fetchall()
        for lst in lists:
            con.execute(
                """INSERT OR IGNORE INTO start_trophies
                   (user_id, subject, group_id, earned_at, silent) VALUES (?,?,?,?,1)""",
                (uid, SUBJECT, lst["list_id"], now),
            )

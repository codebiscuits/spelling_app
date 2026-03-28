import random


def select_words(user_id: int, list_id: int, n: int, db) -> list[int]:
    """
    Weighted sampling of word IDs from list_id for user_id.
    Words with poor history are weighted higher (more likely to appear).
    Uses Efraimidis-Spirakis algorithm (no external deps).
    """
    word_rows = db.execute(
        "SELECT id FROM words WHERE list_id=?", (list_id,)
    ).fetchall()

    if not word_rows:
        return []

    word_ids = [r["id"] for r in word_rows]

    if len(word_ids) <= n:
        random.shuffle(word_ids)
        return word_ids

    # Compute average score per word
    weights = []
    for wid in word_ids:
        rows = db.execute(
            """SELECT session_id,
                      MAX(CASE WHEN attempt_number=1 AND correct=1 THEN 2
                               WHEN attempt_number=2 AND correct=1 THEN 1
                               ELSE 0 END) AS word_score
               FROM spelling_attempts
               WHERE user_id=? AND word_id=?
               GROUP BY session_id""",
            (user_id, wid),
        ).fetchall()
        if rows:
            avg = sum(r["word_score"] for r in rows) / len(rows)
        else:
            avg = 1.0  # unseen → neutral midpoint of 0–2 range
        weight = 1.0 / (avg + 0.5)
        weights.append(weight)

    # Efraimidis-Spirakis: key = u^(1/w), take top n
    keyed = [(random.random() ** (1.0 / w), wid) for w, wid in zip(weights, word_ids)]
    keyed.sort(reverse=True)
    return [wid for _, wid in keyed[:n]]

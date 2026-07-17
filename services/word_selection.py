import random


def select_words(user_id: int, list_ids: list[int], n: int, db,
                 exclude: set[int] | None = None) -> list[int]:
    """
    Weighted sampling of word IDs from list_ids for user_id.
    Words with poor history are weighted higher (more likely to appear).
    Uses Efraimidis-Spirakis algorithm (no external deps).
    Word IDs in `exclude` are never returned.
    """
    if not list_ids:
        return []

    placeholders = ",".join("?" * len(list_ids))
    word_rows = db.execute(
        f"SELECT id FROM words WHERE list_id IN ({placeholders})", list_ids
    ).fetchall()

    exclude = exclude or set()
    word_ids = [r["id"] for r in word_rows if r["id"] not in exclude]

    if not word_ids:
        return []

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
                               WHEN attempt_number=3 AND correct=1 THEN 1
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

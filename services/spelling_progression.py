"""Per-word spelling progression: which words a child practises next.

Vocabulary (see the learning-practice design):

* An *ordinary first attempt* is a spelling_attempts row with
  attempt_number=1. Second attempts (2) and top-ups (3) are never evidence.
* *Mastered*: the latest three ordinary first attempts were all correct.
* *Seen but not mastered*: at least one ordinary first attempt, not mastered.
* *Locked*: no ordinary first attempt yet.
* *Focus*: the one word being introduced. It appears in every ordinary
  practice until it has three first-try-correct appearances in a row.

Everything here is deterministic. Order comes from the explicit position
columns on word_lists and words, never from alphabet or insertion order.
Recency is measured by attempt id, which only ever grows.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

PRACTICE_SIZE = 10
FOCUS_SLOTS = 1
WEAK_SLOTS = 5
STALE_SLOTS = 4
ELIGIBLE_AFTER = 5     # ordinary first attempts before a word can rank as weak
MASTERY_RUN = 3        # consecutive correct first attempts that mean mastered
SUBJECT = "spelling"

# word_id -> [(attempt_id, correct), ...] oldest first
History = dict[int, list[tuple[int, int]]]


@dataclass
class Plan:
    word_ids: list[int]
    focus_id: int | None = None
    kind: str = "normal"                      # 'baseline' | 'normal' | 'empty'
    introduced: list[int] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_history(user_id: int, db) -> History:
    hist: History = {}
    rows = db.execute(
        """SELECT id, word_id, correct FROM spelling_attempts
           WHERE user_id=? AND attempt_number=1 ORDER BY id""",
        (user_id,),
    ).fetchall()
    for r in rows:
        hist.setdefault(r["word_id"], []).append((r["id"], r["correct"]))
    return hist


def is_mastered(entries: list[tuple[int, int]]) -> bool:
    return len(entries) >= MASTERY_RUN and all(c for _, c in entries[-MASTERY_RUN:])


def mastered_word_ids(hist: History) -> set[int]:
    return {w for w, e in hist.items() if is_mastered(e)}


def _recent_accuracy(entries: list[tuple[int, int]]) -> float:
    last = entries[-ELIGIBLE_AFTER:]
    return sum(c for _, c in last) / len(last)


# ── Lists ──────────────────────────────────────────────────────────────────

def available_list_ids(user_id: int, db) -> list[int]:
    rows = db.execute(
        """SELECT ul.list_id FROM user_list_unlocks ul
           JOIN word_lists wl ON wl.id=ul.list_id
           WHERE ul.user_id=? ORDER BY wl.position, wl.id""",
        (user_id,),
    ).fetchall()
    return [r["list_id"] for r in rows]


def _unlock(user_id: int, list_id: int, db, now: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
        (user_id, list_id, now),
    )


def ensure_available_lists(user_id: int, db, now: str | None = None) -> list[int]:
    """A child with no lists gets the earliest list that has words."""
    ids = available_list_ids(user_id, db)
    if ids:
        return ids
    first = db.execute(
        """SELECT wl.id FROM word_lists wl
           WHERE EXISTS (SELECT 1 FROM words w WHERE w.list_id=wl.id)
           ORDER BY wl.position, wl.id LIMIT 1"""
    ).fetchone()
    if not first:
        return []
    _unlock(user_id, first["id"], db, now or _now())
    return [first["id"]]


def _unlock_next_list(user_id: int, db, now: str) -> int | None:
    """Unlock the first list (with words) after the child's furthest list in
    curriculum order. Returns its id, or None when there is no later list."""
    row = db.execute(
        """SELECT COALESCE(MAX(wl.position), 0) AS p FROM user_list_unlocks ul
           JOIN word_lists wl ON wl.id=ul.list_id WHERE ul.user_id=?""",
        (user_id,),
    ).fetchone()
    nxt = db.execute(
        """SELECT wl.id FROM word_lists wl
           WHERE wl.position > ?
             AND EXISTS (SELECT 1 FROM words w WHERE w.list_id=wl.id)
           ORDER BY wl.position, wl.id LIMIT 1""",
        (row["p"],),
    ).fetchone()
    if not nxt:
        return None
    _unlock(user_id, nxt["id"], db, now)
    return nxt["id"]


def curriculum_word_ids(list_ids: list[int], db) -> list[int]:
    """Word ids of the given lists in curriculum order."""
    if not list_ids:
        return []
    marks = ",".join("?" * len(list_ids))
    rows = db.execute(
        f"""SELECT w.id FROM words w JOIN word_lists wl ON wl.id=w.list_id
            WHERE w.list_id IN ({marks})
            ORDER BY wl.position, wl.id, w.position, w.id""",
        list_ids,
    ).fetchall()
    return [r["id"] for r in rows]


# ── Focus ──────────────────────────────────────────────────────────────────

def open_focus(user_id: int, db) -> int | None:
    row = db.execute(
        "SELECT word_id FROM spelling_focus WHERE user_id=? AND completed_at IS NULL",
        (user_id,),
    ).fetchone()
    return row["word_id"] if row else None


def refresh_focus(user_id: int, db, hist: History | None = None, now: str | None = None) -> None:
    """Close the open focus once its word has three first-try-correct
    appearances in a row since it became focus."""
    row = db.execute(
        """SELECT word_id, after_attempt_id FROM spelling_focus
           WHERE user_id=? AND completed_at IS NULL""",
        (user_id,),
    ).fetchone()
    if not row:
        return
    hist = hist if hist is not None else load_history(user_id, db)
    run = 0
    for attempt_id, correct in hist.get(row["word_id"], []):
        if attempt_id <= row["after_attempt_id"]:
            continue
        run = run + 1 if correct else 0
        if run >= MASTERY_RUN:
            db.execute(
                """UPDATE spelling_focus SET completed_at=?
                   WHERE user_id=? AND word_id=? AND completed_at IS NULL""",
                (now or _now(), user_id, row["word_id"]),
            )
            return


def _start_focus(user_id: int, word_id: int, db, now: str) -> None:
    newest = db.execute(
        "SELECT COALESCE(MAX(id),0) AS m FROM spelling_attempts WHERE user_id=?", (user_id,)
    ).fetchone()["m"]
    db.execute(
        """INSERT OR REPLACE INTO spelling_focus
           (user_id, word_id, started_at, completed_at, after_attempt_id)
           VALUES (?,?,?,NULL,?)""",
        (user_id, word_id, now, newest),
    )


# ── Pools ──────────────────────────────────────────────────────────────────

@dataclass
class Pools:
    weak: list[int]                # seen, not mastered, eligible; weakest first
    stale: list[int]               # mastered; longest since practice first
    other_seen: list[int]          # seen, not mastered, not yet eligible; stalest first
    seen_not_mastered: list[int]   # all seen, not mastered; stalest first


def build_pools(hist: History, ordered_ids: list[int], exclude: set[int] | None = None) -> Pools:
    """Split the seen words of ordered_ids (curriculum order) into pools.
    `exclude` words are left out of every pool. Ties fall back to
    curriculum order, so the result never depends on dict or row order."""
    exclude = exclude or set()
    rank = {w: i for i, w in enumerate(ordered_ids)}
    seen = [w for w in ordered_ids if w in hist and w not in exclude]
    mastered = [w for w in seen if is_mastered(hist[w])]
    snm = [w for w in seen if not is_mastered(hist[w])]

    def last_seen(w: int) -> int:
        return hist[w][-1][0]

    eligible = [w for w in snm if len(hist[w]) >= ELIGIBLE_AFTER]
    weak = sorted(eligible, key=lambda w: (_recent_accuracy(hist[w]), last_seen(w), rank[w]))
    stale = sorted(mastered, key=lambda w: (last_seen(w), rank[w]))
    not_eligible = [w for w in snm if len(hist[w]) < ELIGIBLE_AFTER]
    other = sorted(not_eligible, key=lambda w: (last_seen(w), rank[w]))
    return Pools(weak=weak, stale=stale, other_seen=other,
                 seen_not_mastered=sorted(snm, key=lambda w: (last_seen(w), rank[w])))


def _fill_vacancy(count: int, hist: History, ordered_ids: list[int], used: set[int]) -> list[int]:
    """Fill `count` vacant places: other seen-not-mastered words first
    (stalest first), then mastered words (stalest first). Never a locked word."""
    if count <= 0:
        return []
    pools = build_pools(hist, ordered_ids, exclude=used)
    out = pools.seen_not_mastered[:count]
    if len(out) < count:
        out += pools.stale[: count - len(out)]
    return out


# ── Planning ───────────────────────────────────────────────────────────────

def plan_practice(user_id: int, db, n: int = PRACTICE_SIZE, now: str | None = None) -> Plan:
    """Choose the words for one ordinary practice, updating focus and list
    availability as the design requires. Writes only through `db`."""
    now = now or _now()
    list_ids = ensure_available_lists(user_id, db, now)
    if not list_ids:
        return Plan([], kind="empty")

    hist = load_history(user_id, db)
    ordered = curriculum_word_ids(list_ids, db)

    # Baseline: no ordinary attempt at all -> the ten earliest locked words.
    if not hist:
        return Plan(ordered[:n], None, "baseline", introduced=ordered[:n])

    refresh_focus(user_id, db, hist, now)
    focus = open_focus(user_id, db)

    def locked_words() -> list[int]:
        return [w for w in ordered if w not in hist and w != focus]

    locked = locked_words()
    # Every word in the available lists introduced: open the next list.
    while not locked:
        if _unlock_next_list(user_id, db, now) is None:
            break
        list_ids = available_list_ids(user_id, db)
        ordered = curriculum_word_ids(list_ids, db)
        locked = locked_words()

    introduced: list[int] = []
    if focus is None and locked:
        focus = locked[0]
        _start_focus(user_id, focus, db, now)
        introduced.append(focus)

    weak_slots = WEAK_SLOTS + (0 if focus is not None else FOCUS_SLOTS)
    pools = build_pools(hist, ordered, exclude={focus} if focus is not None else set())
    weak = pools.weak[:weak_slots]
    stale = pools.stale[:STALE_SLOTS]
    chosen = ([focus] if focus is not None else []) + weak + stale
    used = set(chosen)
    chosen += _fill_vacancy(weak_slots - len(weak), hist, ordered, used)
    used = set(chosen)
    chosen += _fill_vacancy(STALE_SLOTS - len(stale), hist, ordered, used)
    return Plan(chosen[:n], focus, "normal", introduced=introduced)


def topup_candidates(user_id: int, db, exclude: set[int]) -> list[int]:
    """Words to offer as top-ups, best first: weakest eligible, then
    longest-unpractised mastered, then other seen words. Locked words are
    never offered. `exclude` holds everything already used in this practice."""
    list_ids = available_list_ids(user_id, db)
    ordered = curriculum_word_ids(list_ids, db)
    hist = load_history(user_id, db)
    pools = build_pools(hist, ordered, exclude=exclude)
    return pools.weak + pools.stale + pools.other_seen


def next_topup_word(user_id: int, db, exclude: set[int]) -> int | None:
    cands = topup_candidates(user_id, db, exclude)
    return cands[0] if cands else None


def is_introduction(user_id: int, word_id: int, session_id: int, db) -> bool:
    """True when this practice holds the word's first ordinary appearance."""
    first = db.execute(
        """SELECT session_id FROM spelling_attempts
           WHERE user_id=? AND word_id=? AND attempt_number=1
           ORDER BY id LIMIT 1""",
        (user_id, word_id),
    ).fetchone()
    return first is None or first["session_id"] == session_id

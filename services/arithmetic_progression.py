"""Per-direction arithmetic progression: which questions a child practises next.

It follows services/spelling_progression.py. Differences:

* The unit is a *direction* (see arithmetic_facts), keyed by text.
* The focus is a whole *family*. Each of its directions leaves the focus
  slots on its own, after three first-try-correct appearances in a row since
  the family became focus. The family stays focus until every direction has
  left. The next ordinary practice then introduces the next family.
* Tables open along a ladder. The next rung opens only when every direction
  that belongs to the latest rung is currently secure. Rungs never lock.

Evidence is arithmetic_attempts rows with attempt_number=1 (ordinary first
attempts). Second attempts (2) and top-ups (3) are never evidence.
Recency is measured by attempt id, which only ever grows.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.arithmetic_facts import (
    FACT_ORDER, FACTS, FAMILIES, FAMILY_ORDER, FAMILY_RUNG, LAST_RUNG,
    families_up_to_rung, facts_of_rung,
)

PRACTICE_SIZE = 10
ELIGIBLE_AFTER = 5     # ordinary first attempts before a direction can rank as weak
SECURE_RUN = 3         # consecutive correct first attempts that mean secure
SUBJECT = "arithmetic"
# (weak, stale) slots by situation; focus slots = size of the focus family
SLOTS_FOUR = (3, 3)
SLOTS_SQUARE = (4, 4)
SLOTS_NO_FOCUS = (6, 4)

History = dict[str, list[tuple[int, int]]]   # fact_key -> [(attempt_id, correct)] oldest first
_ORDER_RANK = {k: i for i, k in enumerate(FACT_ORDER)}


@dataclass
class Plan:
    fact_keys: list[str]
    focus_family: str | None = None
    kind: str = "normal"                      # 'baseline' | 'normal'
    introduced: list[str] = field(default_factory=list)   # directions new to the child


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_history(user_id: int, db) -> History:
    hist: History = {}
    rows = db.execute(
        """SELECT id, fact_key, correct FROM arithmetic_attempts
           WHERE user_id=? AND attempt_number=1 ORDER BY id""",
        (user_id,),
    ).fetchall()
    for r in rows:
        hist.setdefault(r["fact_key"], []).append((r["id"], r["correct"]))
    return hist


def is_secure(entries: list[tuple[int, int]]) -> bool:
    return len(entries) >= SECURE_RUN and all(c for _, c in entries[-SECURE_RUN:])


def secure_keys(hist: History) -> set[str]:
    return {k for k, e in hist.items() if is_secure(e)}


def _recent_accuracy(entries: list[tuple[int, int]]) -> float:
    last = entries[-ELIGIBLE_AFTER:]
    return sum(c for _, c in last) / len(last)


# ── Rungs ──────────────────────────────────────────────────────────────────

def unlocked_rungs(user_id: int, db) -> list[int]:
    rows = db.execute(
        "SELECT rung FROM arithmetic_rungs WHERE user_id=? ORDER BY rung", (user_id,)
    ).fetchall()
    return [r["rung"] for r in rows]


def latest_rung(user_id: int, db) -> int:
    rungs = unlocked_rungs(user_id, db)
    return rungs[-1] if rungs else 0


def ensure_first_rung(user_id: int, db, now: str | None = None) -> None:
    db.execute(
        "INSERT OR IGNORE INTO arithmetic_rungs (user_id, rung, unlocked_at) VALUES (?,1,?)",
        (user_id, now or _now()),
    )


def rung_complete(rung: int, hist: History) -> bool:
    """Every direction that belongs to this rung is currently secure."""
    return all(is_secure(hist.get(k, [])) for k in facts_of_rung(rung))


def unlock_rungs(user_id: int, db, hist: History, now: str | None = None) -> list[int]:
    """Open the next rung while the latest rung is complete. Returns the
    rungs opened now. A demoted direction blocks it; opened rungs stay open."""
    opened = []
    current = latest_rung(user_id, db)
    while 0 < current < LAST_RUNG and rung_complete(current, hist):
        current += 1
        db.execute(
            "INSERT OR IGNORE INTO arithmetic_rungs (user_id, rung, unlocked_at) VALUES (?,?,?)",
            (user_id, current, now or _now()),
        )
        opened.append(current)
    return opened


def available_families(user_id: int, db) -> list[str]:
    return families_up_to_rung(latest_rung(user_id, db))


def available_fact_keys(user_id: int, db) -> list[str]:
    return [f.key for fam in available_families(user_id, db) for f in FAMILIES[fam]]


# ── Introduced families and focus ──────────────────────────────────────────

def _introduced_families(user_id: int, db, hist: History) -> set[str]:
    """A family is introduced when it has had a focus row, or when every
    one of its directions has been attempted (as in the baseline)."""
    rows = db.execute(
        "SELECT family_key FROM arithmetic_focus WHERE user_id=?", (user_id,)
    ).fetchall()
    done = {r["family_key"] for r in rows}
    for fam, facts in FAMILIES.items():
        if all(f.key in hist for f in facts):
            done.add(fam)
    return done


def next_family_to_introduce(user_id: int, db, hist: History) -> str | None:
    done = _introduced_families(user_id, db, hist)
    for fam in available_families(user_id, db):
        if fam not in done:
            return fam
    return None


def open_focus(user_id: int, db) -> str | None:
    row = db.execute(
        "SELECT family_key FROM arithmetic_focus WHERE user_id=? AND completed_at IS NULL",
        (user_id,),
    ).fetchone()
    return row["family_key"] if row else None


def _focus_after(user_id: int, family: str, db) -> int:
    row = db.execute(
        "SELECT after_attempt_id FROM arithmetic_focus WHERE user_id=? AND family_key=?",
        (user_id, family),
    ).fetchone()
    return row["after_attempt_id"] if row else 0


def has_left_focus(entries: list[tuple[int, int]], after_attempt_id: int) -> bool:
    """Three first-try-correct appearances in a row since the family
    became focus."""
    run = 0
    for attempt_id, correct in entries:
        if attempt_id <= after_attempt_id:
            continue
        run = run + 1 if correct else 0
        if run >= SECURE_RUN:
            return True
    return False


def focus_remaining(user_id: int, family: str, db, hist: History) -> list[str]:
    """Directions of the focus family still in the focus slots, in order."""
    after = _focus_after(user_id, family, db)
    return [f.key for f in FAMILIES[family]
            if not has_left_focus(hist.get(f.key, []), after)]


def refresh_focus(user_id: int, db, hist: History | None = None, now: str | None = None) -> None:
    """Close the open focus family once every direction has left."""
    fam = open_focus(user_id, db)
    if fam is None:
        return
    hist = hist if hist is not None else load_history(user_id, db)
    if not focus_remaining(user_id, fam, db, hist):
        db.execute(
            """UPDATE arithmetic_focus SET completed_at=?
               WHERE user_id=? AND family_key=? AND completed_at IS NULL""",
            (now or _now(), user_id, fam),
        )


def _start_focus(user_id: int, family: str, db, now: str) -> None:
    newest = db.execute(
        "SELECT COALESCE(MAX(id),0) AS m FROM arithmetic_attempts WHERE user_id=?", (user_id,)
    ).fetchone()["m"]
    db.execute(
        """INSERT OR REPLACE INTO arithmetic_focus
           (user_id, family_key, started_at, completed_at, after_attempt_id)
           VALUES (?,?,?,NULL,?)""",
        (user_id, family, now, newest),
    )


# ── Pools ──────────────────────────────────────────────────────────────────

@dataclass
class Pools:
    weak: list[str]                # seen, insecure, eligible; weakest first
    stale: list[str]               # secure; longest since practice first
    other_seen: list[str]          # seen, insecure, not yet eligible; stalest first
    seen_insecure: list[str]       # all seen, insecure; stalest first


def build_pools(hist: History, exclude: set[str] | None = None) -> Pools:
    """Split the seen directions into pools. `exclude` directions are left
    out of every pool. Ties fall back to the fixed order, so the result
    never depends on dict or row order."""
    exclude = exclude or set()
    seen = [k for k in FACT_ORDER if k in hist and k not in exclude]
    secure = [k for k in seen if is_secure(hist[k])]
    insecure = [k for k in seen if not is_secure(hist[k])]

    def last_seen(k: str) -> int:
        return hist[k][-1][0]

    eligible = [k for k in insecure if len(hist[k]) >= ELIGIBLE_AFTER]
    weak = sorted(eligible, key=lambda k: (_recent_accuracy(hist[k]), last_seen(k), _ORDER_RANK[k]))
    stale = sorted(secure, key=lambda k: (last_seen(k), _ORDER_RANK[k]))
    other = sorted((k for k in insecure if len(hist[k]) < ELIGIBLE_AFTER),
                   key=lambda k: (last_seen(k), _ORDER_RANK[k]))
    return Pools(weak=weak, stale=stale, other_seen=other,
                 seen_insecure=sorted(insecure, key=lambda k: (last_seen(k), _ORDER_RANK[k])))


def _fill_vacancy(count: int, hist: History, used: set[str]) -> list[str]:
    """Fill vacant places: other insecure seen directions first (stalest
    first), then secure ones. Never an unseen direction."""
    if count <= 0:
        return []
    pools = build_pools(hist, exclude=used)
    out = pools.seen_insecure[:count]
    if len(out) < count:
        out += pools.stale[: count - len(out)]
    return out


# ── Planning ───────────────────────────────────────────────────────────────

def baseline_keys(n: int = PRACTICE_SIZE) -> list[str]:
    """The first rung-1 families in the fixed order, whole families only:
    a family that does not fit in the places left is skipped, so no family
    is ever half-included. With n=10 this is 2x2, 2x3 and 2x4 (2+4+4)."""
    chosen: list[str] = []
    for fam in FAMILY_ORDER:
        if FAMILY_RUNG[fam] != 1:
            break
        keys = [f.key for f in FAMILIES[fam]]
        if len(chosen) + len(keys) <= n:
            chosen += keys
        if len(chosen) == n:
            break
    return chosen


def plan_practice(user_id: int, db, n: int = PRACTICE_SIZE, now: str | None = None) -> Plan:
    """Choose the directions for one ordinary practice, updating the rungs
    and focus as the design requires. Writes only through `db`."""
    now = now or _now()
    ensure_first_rung(user_id, db, now)
    hist = load_history(user_id, db)

    if not hist:
        keys = baseline_keys(n)
        return Plan(keys, None, "baseline", introduced=list(keys))

    refresh_focus(user_id, db, hist, now)
    unlock_rungs(user_id, db, hist, now)

    introduced: list[str] = []
    family = open_focus(user_id, db)
    if family is None:
        family = next_family_to_introduce(user_id, db, hist)
        if family is not None:
            _start_focus(user_id, family, db, now)
            introduced = [f.key for f in FAMILIES[family] if f.key not in hist]

    if family is not None:
        remaining = focus_remaining(user_id, family, db, hist)
        size = len(FAMILIES[family])
        weak_n, stale_n = SLOTS_SQUARE if size == 2 else SLOTS_FOUR
        weak_n += size - len(remaining)          # freed focus slots go to weak
    else:
        remaining = []
        weak_n, stale_n = SLOTS_NO_FOCUS

    pools = build_pools(hist, exclude=set(remaining))
    weak = pools.weak[:weak_n]
    stale = pools.stale[:stale_n]
    chosen = remaining + weak + stale
    chosen += _fill_vacancy(weak_n - len(weak), hist, set(chosen))
    chosen += _fill_vacancy(stale_n - len(stale), hist, set(chosen))
    return Plan(chosen[:n], family, "normal", introduced=introduced)


def topup_candidates(user_id: int, db, exclude: set[str]) -> list[str]:
    """Directions to offer as top-ups, best first: weakest eligible, then
    longest-unpractised secure, then other seen ones. Unseen directions
    are never offered. `exclude` holds everything already used."""
    hist = load_history(user_id, db)
    pools = build_pools(hist, exclude=exclude)
    return pools.weak + pools.stale + pools.other_seen


def next_topup_fact(user_id: int, db, exclude: set[str]) -> str | None:
    cands = topup_candidates(user_id, db, exclude)
    return cands[0] if cands else None


def is_introduction(user_id: int, fact_key: str, session_id: int, db) -> bool:
    """True when this practice holds the direction's first ordinary appearance."""
    first = db.execute(
        """SELECT session_id FROM arithmetic_attempts
           WHERE user_id=? AND fact_key=? AND attempt_number=1
           ORDER BY id LIMIT 1""",
        (user_id, fact_key),
    ).fetchone()
    return first is None or first["session_id"] == session_id


def started_rungs(user_id: int, db) -> list[tuple[int, int]]:
    """(rung, first attempt id) for each rung with an ordinary first attempt
    at a direction of one of its families, in rung order."""
    first: dict[int, int] = {}
    rows = db.execute(
        """SELECT fact_key, MIN(id) AS first_id FROM arithmetic_attempts
           WHERE user_id=? AND attempt_number=1 GROUP BY fact_key""",
        (user_id,),
    ).fetchall()
    for r in rows:
        rung = FAMILY_RUNG[FACTS[r["fact_key"]].family]
        if rung not in first or r["first_id"] < first[rung]:
            first[rung] = r["first_id"]
    return sorted(first.items())

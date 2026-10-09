"""Read-only progress monitoring for the admin pages.

Nothing here writes to the database or needs a schema change. It reads
the evidence the practices already record, and uses the progression
services' own definitions of "mastered" and "secure" so the admin view and
the practice selector can never disagree.

Evidence rules (see the learning-practice design):

* An *ordinary practice* is a test_sessions row of the subject.
* *Ordinary first attempts* have attempt_number=1. Second attempts (2) and
  top-ups (3) never count towards the charts.
* A practice is *completed* (and gets a chart point) when it holds at least
  PRACTICE_SIZE ordinary first attempts. A practice that was abandoned part
  way is listed in the history but not charted. Its first attempts still
  count as evidence, exactly as they do in the selector.
"""
from datetime import datetime, timedelta, timezone
from statistics import median

from services import arithmetic_progression as arith
from services import spelling_progression as spell
from services.arithmetic_facts import FACT_ORDER, FACTS, LADDER

PRACTICE_SIZE = 10
RECENT_DAYS = 7
SPELLING = "spelling"
ARITHMETIC = "arithmetic"

# Table and column names come from this constant dict only, never from a
# request, so building SQL with them is safe.
_CONFIG = {
    SPELLING: {"table": "spelling_attempts", "key": "word_id",
               "ms": "NULL", "is_secure": spell.is_mastered},
    ARITHMETIC: {"table": "arithmetic_attempts", "key": "fact_key",
                 "ms": "response_ms", "is_secure": arith.is_secure},
}


def _percent(correct: int, total: int) -> float | None:
    return round(100 * correct / total, 1) if total else None


# ── Practice history and the cumulative counts ─────────────────────────────

def practice_history(db, user_id: int, subject: str) -> list[dict]:
    """One dict per practice of the subject, oldest first.

    The secure count after each practice is computed in one pass over the
    child's ordinary first attempts in attempt-id order (the order the
    selector uses). Each item keeps its attempt list, and the counts change
    only when the item just attempted changes status. A snapshot is taken
    when a practice's last ordinary first attempt has been processed. That
    is O(attempts) with a single query, not one query per chart point.
    """
    cfg = _CONFIG[subject]
    is_secure = cfg["is_secure"]
    sessions = db.execute(
        """SELECT id, timestamp, score, max_score FROM test_sessions
           WHERE user_id=? AND subject=? ORDER BY timestamp, id""",
        (user_id, subject),
    ).fetchall()
    rows = db.execute(
        f"""SELECT id, session_id, {cfg['key']} AS item, correct, {cfg['ms']} AS ms
            FROM {cfg['table']}
            WHERE user_id=? AND attempt_number=1 ORDER BY id""",
        (user_id,),
    ).fetchall()

    last_row: dict[int, int] = {}
    for i, r in enumerate(rows):
        last_row[r["session_id"]] = i

    stats: dict[int, dict] = {}
    snapshot: dict[int, tuple[int, int]] = {}
    items: dict = {}
    secure = 0
    for i, r in enumerate(rows):
        st = stats.setdefault(r["session_id"], {"n": 0, "ok": 0, "ms": []})
        st["n"] += 1
        st["ok"] += r["correct"]
        if r["correct"] and r["ms"] is not None:
            st["ms"].append(r["ms"])

        entries = items.setdefault(r["item"], [])
        before = is_secure(entries)
        entries.append((r["id"], r["correct"]))
        after = is_secure(entries)
        secure += int(after) - int(before)
        if last_row[r["session_id"]] == i:
            snapshot[r["session_id"]] = (secure, len(items) - secure)

    history = []
    for s in sessions:
        st = stats.get(s["id"], {"n": 0, "ok": 0, "ms": []})
        secure_n, review_n = snapshot.get(s["id"], (None, None))
        history.append({
            "session_id": s["id"],
            "timestamp": s["timestamp"],
            "date": s["timestamp"][:10],
            "score": s["score"],
            "max_score": s["max_score"],
            "n_first": st["n"],
            "n_correct": st["ok"],
            "accuracy": _percent(st["ok"], st["n"]),
            "secure": secure_n,
            "review": review_n,
            "median_s": round(median(st["ms"]) / 1000, 2) if st["ms"] else None,
            "completed": st["n"] >= PRACTICE_SIZE,
        })
    return history


def completed_practices(history: list[dict]) -> list[dict]:
    return [p for p in history if p["completed"]]


def chart_payload(subject: str, history: list[dict], child_id: int) -> dict:
    """The JSON the chart script reads: one entry per completed practice."""
    pts = completed_practices(history)
    base = f"/admin/children/{child_id}/{subject}/practices/"
    payload = {
        "subject": subject,
        "labels": [p["date"] for p in pts],
        "urls": [base + str(p["session_id"]) for p in pts],
        "accuracy": [p["accuracy"] for p in pts],
        "secure": [p["secure"] for p in pts],
        "review": [p["review"] for p in pts],
    }
    if subject == ARITHMETIC:
        payload["median_s"] = [p["median_s"] for p in pts]
    return payload


# ── Overview ───────────────────────────────────────────────────────────────

def subject_summary(db, user_id: int, subject: str, now: datetime | None = None) -> dict:
    history = practice_history(db, user_id, subject)
    done = completed_practices(history)
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=RECENT_DAYS)).isoformat()
    last = done[-1] if done else None
    return {
        "practices": len(done),
        "last_date": last["date"] if last else None,
        "secure": last["secure"] if last else 0,
        "review": last["review"] if last else 0,
        "recent": sum(1 for p in done if p["timestamp"] >= cutoff),
    }


# ── Items ──────────────────────────────────────────────────────────────────

def item_history(db, user_id: int, subject: str, item) -> list[dict]:
    """Every ordinary first attempt at one item, oldest first."""
    cfg = _CONFIG[subject]
    rows = db.execute(
        f"""SELECT id, session_id, timestamp, correct, {cfg['ms']} AS ms
            FROM {cfg['table']}
            WHERE user_id=? AND {cfg['key']}=? AND attempt_number=1 ORDER BY id""",
        (user_id, item),
    ).fetchall()
    return [dict(r) for r in rows]


def status_label(secure: bool, seen: bool, subject: str) -> str:
    if secure:
        return "Mastered" if subject == SPELLING else "Secure"
    return "Needing review" if seen else "Not yet introduced"


def accuracy_text(entries: list[dict]) -> str:
    last = entries[-spell.ELIGIBLE_AFTER:]
    if not last:
        return "-"
    return f"{sum(e['correct'] for e in last)}/{len(last)}"


def spelling_item_rows(db, user_id: int) -> list[dict]:
    """The words the child has seen, with status and recent accuracy."""
    rows = db.execute(
        """SELECT sa.id, sa.word_id, sa.timestamp, sa.correct, w.word, wl.name AS list_name
           FROM spelling_attempts sa
           JOIN words w ON w.id=sa.word_id JOIN word_lists wl ON wl.id=w.list_id
           WHERE sa.user_id=? AND sa.attempt_number=1 ORDER BY sa.id""",
        (user_id,),
    ).fetchall()
    focus = spell.open_focus(user_id, db)
    by_word: dict[int, dict] = {}
    for r in rows:
        d = by_word.setdefault(r["word_id"], {
            "id": r["word_id"], "label": r["word"], "list_name": r["list_name"], "entries": []})
        d["entries"].append({"id": r["id"], "correct": r["correct"], "timestamp": r["timestamp"]})
    out = []
    for d in by_word.values():
        pairs = [(e["id"], e["correct"]) for e in d["entries"]]
        mastered = spell.is_mastered(pairs)
        out.append({
            "id": d["id"], "label": d["label"], "group": d["list_name"],
            "status": status_label(mastered, True, SPELLING),
            "secure": mastered,
            "focus": d["id"] == focus,
            "attempts": len(pairs),
            "recent": accuracy_text(d["entries"]),
            "last_date": d["entries"][-1]["timestamp"][:10],
        })
    out.sort(key=lambda x: (x["secure"], x["label"]))
    return out


def arithmetic_item_rows(db, user_id: int) -> list[dict]:
    rows = db.execute(
        """SELECT id, fact_key, timestamp, correct FROM arithmetic_attempts
           WHERE user_id=? AND attempt_number=1 ORDER BY id""",
        (user_id,),
    ).fetchall()
    focus_keys = focus_directions(db, user_id)
    by_key: dict[str, list[dict]] = {}
    for r in rows:
        by_key.setdefault(r["fact_key"], []).append(
            {"id": r["id"], "correct": r["correct"], "timestamp": r["timestamp"]})
    out = []
    for key in FACT_ORDER:
        entries = by_key.get(key)
        if not entries:
            continue
        pairs = [(e["id"], e["correct"]) for e in entries]
        secure = arith.is_secure(pairs)
        out.append({
            "id": key, "label": FACTS[key].text + f" = {FACTS[key].answer}",
            "group": family_label(FACTS[key].family),
            "status": status_label(secure, True, ARITHMETIC),
            "secure": secure,
            "focus": key in focus_keys,
            "attempts": len(pairs),
            "recent": accuracy_text(entries),
            "last_date": entries[-1]["timestamp"][:10],
        })
    out.sort(key=lambda x: (x["secure"], FACT_ORDER.index(x["id"])))
    return out


# ── Arithmetic position ────────────────────────────────────────────────────

def family_label(family: str) -> str:
    """'f:3x4' -> '3 x 4 family'."""
    a, b = family[2:].split("x")
    return f"{a} × {b} family"


def focus_directions(db, user_id: int) -> list[str]:
    """Directions still in the focus slots of the open focus family."""
    fam = arith.open_focus(user_id, db)
    if fam is None:
        return []
    return arith.focus_remaining(user_id, fam, db, arith.load_history(user_id, db))


def arithmetic_position(db, user_id: int) -> dict:
    rung = arith.latest_rung(user_id, db)
    tables = sorted(t for r in range(rung) for t in LADDER[r])
    fam = arith.open_focus(user_id, db)
    return {
        "rung": rung,
        "tables": tables,
        "focus_family": family_label(fam) if fam else None,
        "focus_directions": [FACTS[k].text for k in focus_directions(db, user_id)],
    }


# ── One practice's evidence ────────────────────────────────────────────────

def practice_evidence(db, user_id: int, subject: str, session_id: int) -> dict | None:
    """Items asked in order, with first and second attempts, and top-ups
    listed apart. Returns None if the practice is not this child's."""
    cfg = _CONFIG[subject]
    session = db.execute(
        "SELECT * FROM test_sessions WHERE id=? AND user_id=? AND subject=?",
        (session_id, user_id, subject),
    ).fetchone()
    if not session:
        return None
    if subject == SPELLING:
        sql = f"""SELECT a.id, a.{cfg['key']} AS item, a.correct, a.attempt_number,
                         a.timestamp, NULL AS ms, w.word AS label
                  FROM {cfg['table']} a JOIN words w ON w.id=a.word_id
                  WHERE a.session_id=? AND a.user_id=? ORDER BY a.id"""
    else:
        sql = f"""SELECT id, {cfg['key']} AS item, correct, attempt_number,
                         timestamp, {cfg['ms']} AS ms, {cfg['key']} AS label
                  FROM {cfg['table']}
                  WHERE session_id=? AND user_id=? ORDER BY id"""
    rows = db.execute(sql, (session_id, user_id)).fetchall()

    def label(r) -> str:
        return FACTS[r["label"]].text if subject == ARITHMETIC else r["label"]

    asked: dict = {}
    topups = []
    for r in rows:
        ms = r["ms"]
        cell = {"correct": bool(r["correct"]),
                "seconds": round(ms / 1000, 2) if ms is not None else None}
        if r["attempt_number"] == 3:
            topups.append({"item": r["item"], "label": label(r), **cell})
            continue
        row = asked.setdefault(r["item"], {"item": r["item"], "label": label(r),
                                           "first": None, "second": None})
        if r["attempt_number"] == 1:
            row["first"] = cell
        else:
            row["second"] = cell
    items = list(asked.values())
    firsts = [i["first"] for i in items if i["first"]]
    return {
        "session": dict(session),
        "date": session["timestamp"][:10],
        "time": session["timestamp"][11:16],
        "asked": items,
        "topups": topups,
        "n_first": len(firsts),
        "n_correct": sum(f["correct"] for f in firsts),
        "accuracy": _percent(sum(f["correct"] for f in firsts), len(firsts)),
    }

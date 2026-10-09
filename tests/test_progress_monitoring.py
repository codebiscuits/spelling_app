"""Admin progress monitoring: read-only pages over the existing evidence."""
import json
import re

import pytest

from services import progress_monitoring as pm
from services import spelling_progression as spell
from services.arithmetic_facts import FACT_ORDER, FACTS
from tests.conftest import app_db, setup_practice_list

WORDS = [f"word{i}" for i in range(10)]


def make_child(name="Bobby"):
    with app_db() as db:
        return db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            (name, "2016-01-01", "hash", "2025-01-01T00:00:00+00:00"),
        ).lastrowid


def add_session(db, uid, day, subject, score=10):
    return db.execute(
        """INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score, subject)
           VALUES (?,?,NULL,?,20,?)""",
        (f"2026-03-{day:02d}T10:00:00+00:00", uid, score, subject),
    ).lastrowid


def add_spelling(db, uid, sid, word_id, correct, number=1, day=1):
    db.execute(
        """INSERT INTO spelling_attempts
           (timestamp, user_id, word_id, correct, attempt_number, session_id)
           VALUES (?,?,?,?,?,?)""",
        (f"2026-03-{day:02d}T10:00:00+00:00", uid, word_id, correct, number, sid),
    )


def add_arith(db, uid, sid, key, correct, number=1, ms=None, day=1):
    db.execute(
        """INSERT INTO arithmetic_attempts
           (timestamp, user_id, fact_key, correct, attempt_number, session_id, response_ms)
           VALUES (?,?,?,?,?,?,?)""",
        (f"2026-03-{day:02d}T10:00:00+00:00", uid, key, correct, number, sid, ms),
    )


@pytest.fixture
def spelling_child(admin_client):
    """Four completed practices, one unfinished one, and top-ups.

    Mastered / review after each practice: S1 0/10, S2 0/10, S3 5/5,
    S4 9/1. The unfinished practice S5 has 3 answers and no chart point.
    """
    uid = make_child("Sam")
    _, ids = setup_practice_list(uid, WORDS)
    w = [ids[x] for x in WORDS]
    with app_db() as db:
        s1 = add_session(db, uid, 1, "spelling", 12)
        for i, wid in enumerate(w):
            add_spelling(db, uid, s1, wid, 1 if i < 5 else 0, 1, 1)
            if i >= 5:
                add_spelling(db, uid, s1, wid, 1, 2, 1)
        s2 = add_session(db, uid, 2, "spelling")
        for wid in w:
            add_spelling(db, uid, s2, wid, 1, 1, 2)
        s3 = add_session(db, uid, 3, "spelling")
        for wid in w:
            add_spelling(db, uid, s3, wid, 1, 1, 3)
        s4 = add_session(db, uid, 4, "spelling")
        for i, wid in enumerate(w):
            add_spelling(db, uid, s4, wid, 0 if i == 9 else 1, 1, 4)
        # Top-ups: a wrong one on a mastered word. It must change nothing.
        add_spelling(db, uid, s4, w[0], 0, 3, 4)
        add_spelling(db, uid, s4, w[9], 1, 3, 4)
        s5 = add_session(db, uid, 5, "spelling")
        for wid in w[:3]:
            add_spelling(db, uid, s5, wid, 1, 1, 5)
    return {"uid": uid, "w": w, "ids": ids, "sessions": [s1, s2, s3, s4, s5]}


@pytest.fixture
def arith_child(admin_client):
    """Three completed practices over the first ten directions.

    A1: k0 and k1 wrong first (second attempts right, fast), k2..k9 right
    with 3000..10000 ms, so the median of correct firsts is 6.5 s.
    A2: all right at 2000 ms. A3: all right at 4000 ms. Secure after: 0, 0, 8.
    A top-up in A1 is right at 1 ms and must not be counted.
    """
    uid = make_child("Ari")
    keys = FACT_ORDER[:10]
    with app_db() as db:
        a1 = add_session(db, uid, 1, "arithmetic")
        for i, k in enumerate(keys):
            if i < 2:
                add_arith(db, uid, a1, k, 0, 1, 99999, 1)
                add_arith(db, uid, a1, k, 1, 2, 50, 1)
            else:
                add_arith(db, uid, a1, k, 1, 1, (i + 1) * 1000, 1)
        add_arith(db, uid, a1, keys[5], 1, 3, 1, 1)
        a2 = add_session(db, uid, 2, "arithmetic")
        for k in keys:
            add_arith(db, uid, a2, k, 1, 1, 2000, 2)
        a3 = add_session(db, uid, 3, "arithmetic")
        for k in keys:
            add_arith(db, uid, a3, k, 1, 1, 4000, 3)
        db.execute("INSERT INTO arithmetic_rungs (user_id, rung, unlocked_at) VALUES (?,1,'x')", (uid,))
        db.execute("INSERT INTO arithmetic_rungs (user_id, rung, unlocked_at) VALUES (?,2,'x')", (uid,))
        db.execute(
            """INSERT INTO arithmetic_focus (user_id, family_key, started_at, after_attempt_id)
               VALUES (?,?,?,0)""", (uid, "f:2x5", "x"))
    return {"uid": uid, "keys": keys, "sessions": [a1, a2, a3]}


def chart_data(html):
    m = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', html, re.S)
    assert m, "no chart data element"
    return json.loads(m.group(1))


# ── Spelling view ──────────────────────────────────────────────────────────

def test_spelling_chart_series(admin_client, spelling_child):
    sc = spelling_child
    resp = admin_client.get(f"/admin/children/{sc['uid']}/spelling")
    assert resp.status_code == 200
    d = chart_data(resp.text)
    assert d["labels"] == ["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04"]
    assert d["accuracy"] == [50.0, 100.0, 100.0, 90.0]
    assert d["secure"] == [0, 0, 5, 9]
    assert d["review"] == [10, 10, 5, 1]
    assert d["urls"] == [f"/admin/children/{sc['uid']}/spelling/practices/{s}"
                         for s in sc["sessions"][:4]]
    assert "chart.umd" in resp.text            # Chart.js loaded by the base template
    assert "/static/js/admin_progress.js?v=" in resp.text


def test_spelling_cumulative_counts_match_brute_force(admin_client, spelling_child):
    """Each point must equal the selector's own answer on the evidence so far."""
    sc = spelling_child
    with app_db() as db:
        hist = pm.practice_history(db, sc["uid"], "spelling")
        for p in pm.completed_practices(hist):
            rows = db.execute(
                """SELECT id, word_id, correct FROM spelling_attempts
                   WHERE user_id=? AND attempt_number=1 AND session_id<=? ORDER BY id""",
                (sc["uid"], p["session_id"]),
            ).fetchall()
            h = {}
            for r in rows:
                h.setdefault(r["word_id"], []).append((r["id"], r["correct"]))
            assert p["secure"] == len(spell.mastered_word_ids(h))
            assert p["review"] == len(h) - p["secure"]


def test_spelling_history_table_and_unfinished(admin_client, spelling_child):
    sc = spelling_child
    html = admin_client.get(f"/admin/children/{sc['uid']}/spelling").text
    assert "50.0% (5/10)" in html
    assert "90.0% (9/10)" in html
    assert "unfinished, not charted" in html           # the 3-answer practice
    assert "Mastered words</strong>" not in html        # label is plain text, see below
    assert "Mastered words: <strong>9</strong>" in html
    assert "Words needing review: <strong>1</strong>" in html
    assert "Charted practices: <strong>4</strong>" in html


def test_spelling_item_list_links_and_status(admin_client, spelling_child):
    sc = spelling_child
    html = admin_client.get(f"/admin/children/{sc['uid']}/spelling").text
    assert f"/admin/children/{sc['uid']}/spelling/words/{sc['w'][9]}" in html
    assert "Needing review" in html and "Mastered" in html
    assert "word0" in html


# ── Practice evidence ──────────────────────────────────────────────────────

def test_spelling_practice_evidence_first_second_and_topups(admin_client, spelling_child):
    sc = spelling_child
    s1, _, _, s4, _ = sc["sessions"]
    html = admin_client.get(f"/admin/children/{sc['uid']}/spelling/practices/{s1}").text
    assert "word0" in html and "word9" in html
    assert html.count("<tr class=\"correct\">") == 5     # right first time
    assert html.count("<tr class=\"incorrect\">") == 5   # wrong first time, second attempt shown
    assert "No top-ups in this practice." in html
    assert "50.0% (5/10)" in html

    html4 = admin_client.get(f"/admin/children/{sc['uid']}/spelling/practices/{s4}").text
    assert "Top-ups (do not count)" in html4
    assert "No top-ups in this practice." not in html4
    top = html4.split("Top-ups (do not count)")[1]
    assert "word0" in top and "word9" in top
    assert "Wrong" in top and "Right" in top
    assert f"/admin/children/{sc['uid']}/spelling/words/{sc['w'][0]}" in html4


def test_practice_of_another_child_or_subject_is_404(admin_client, spelling_child, arith_child):
    sc, ac = spelling_child, arith_child
    assert admin_client.get(
        f"/admin/children/{ac['uid']}/spelling/practices/{sc['sessions'][0]}").status_code == 404
    assert admin_client.get(
        f"/admin/children/{sc['uid']}/arithmetic/practices/{sc['sessions'][0]}").status_code == 404
    assert admin_client.get(f"/admin/children/{sc['uid']}/spelling/practices/99999").status_code == 404


# ── Item detail ────────────────────────────────────────────────────────────

def test_spelling_item_latest_five_status_and_last_date(admin_client):
    uid = make_child("Lee")
    _, ids = setup_practice_list(uid, ["extra", "untouched"])
    results = [0, 1, 0, 1, 1, 1, 1]       # seven days; the last three are right
    with app_db() as db:
        for day, ok in enumerate(results, start=1):
            sid = add_session(db, uid, day, "spelling")
            add_spelling(db, uid, sid, ids["extra"], ok, 1, day)
            add_spelling(db, uid, sid, ids["extra"], 0, 3, day)     # top-up: ignored
    html = admin_client.get(f"/admin/children/{uid}/spelling/words/{ids['extra']}").text
    assert "Mastered" in html
    assert "Last ordinary practice: 2026-03-07" in html
    assert "Ordinary first attempts so far: 7" in html
    for day in (3, 4, 5, 6, 7):
        assert f"2026-03-0{day}" in html
    for day in (1, 2):
        assert f"2026-03-0{day}" not in html.replace("Last ordinary practice: 2026-03-07", "")
    assert html.count("<tr class=\"correct\">") == 4 and html.count("<tr class=\"incorrect\">") == 1

    fresh = admin_client.get(f"/admin/children/{uid}/spelling/words/{ids['untouched']}").text
    assert "Not yet introduced" in fresh and "never" in fresh


def test_spelling_item_needing_review_focus_and_locked(admin_client):
    uid = make_child("Kim")
    _, ids = setup_practice_list(uid, ["hard"])
    with app_db() as db:
        other = db.execute("INSERT INTO word_lists (name, position) VALUES ('Later', 99)").lastrowid
        locked_id = db.execute(
            "INSERT INTO words (word, list_id, position) VALUES ('lockedword', ?, 1)", (other,)
        ).lastrowid
        sid = add_session(db, uid, 1, "spelling")
        add_spelling(db, uid, sid, ids["hard"], 1, 1, 1)
        add_spelling(db, uid, sid, ids["hard"], 0, 1, 1)
        db.execute(
            "INSERT INTO spelling_focus (user_id, word_id, started_at, after_attempt_id) VALUES (?,?,'x',0)",
            (uid, ids["hard"]))
    html = admin_client.get(f"/admin/children/{uid}/spelling/words/{ids['hard']}").text
    assert "Needing review" in html and "Current focus" in html
    locked = admin_client.get(f"/admin/children/{uid}/spelling/words/{locked_id}").text
    assert "Locked" in locked


# ── Arithmetic view ────────────────────────────────────────────────────────

def test_arithmetic_chart_series(admin_client, arith_child):
    ac = arith_child
    resp = admin_client.get(f"/admin/children/{ac['uid']}/arithmetic")
    assert resp.status_code == 200
    d = chart_data(resp.text)
    assert d["accuracy"] == [80.0, 100.0, 100.0]
    assert d["secure"] == [0, 0, 8]
    # Wrong, second-attempt and top-up times are excluded: median(3000..10000) = 6.5 s
    assert d["median_s"] == [6.5, 2.0, 4.0]
    assert d["urls"][0] == f"/admin/children/{ac['uid']}/arithmetic/practices/{ac['sessions'][0]}"


def test_arithmetic_position_and_history(admin_client, arith_child):
    ac = arith_child
    html = admin_client.get(f"/admin/children/{ac['uid']}/arithmetic").text
    assert "Rung 2." in html
    assert "Tables unlocked: 2, 5, 10" in html
    assert "2 × 5 family" in html
    assert "80.0% (8/10)" in html
    assert "Secure directions: <strong>8</strong>" in html
    assert f"/admin/children/{ac['uid']}/arithmetic/facts?key=" in html


def test_median_skips_point_with_no_correct_timed_attempt(admin_client):
    uid = make_child("Dee")
    keys = FACT_ORDER[:10]
    with app_db() as db:
        sid = add_session(db, uid, 1, "arithmetic")
        for k in keys:
            add_arith(db, uid, sid, k, 1, 1, None)          # no times recorded
    d = chart_data(admin_client.get(f"/admin/children/{uid}/arithmetic").text)
    assert d["median_s"] == [None]
    assert d["accuracy"] == [100.0]                          # one-point chart is fine


def test_arithmetic_practice_evidence(admin_client, arith_child):
    ac = arith_child
    html = admin_client.get(
        f"/admin/children/{ac['uid']}/arithmetic/practices/{ac['sessions'][0]}").text
    assert FACTS[ac["keys"][0]].text in html
    assert "100.0" in html and "0.05" in html              # first and second times, in seconds
    assert "3.0" in html and "10.0" in html
    assert html.count("<tr class=\"incorrect\">") == 2
    assert "Top-ups (do not count)" in html
    assert "0.0" in html.split("Top-ups (do not count)")[1]  # the 1 ms top-up


def test_arithmetic_item_detail(admin_client, arith_child):
    ac = arith_child
    k = ac["keys"][5]
    html = admin_client.get(f"/admin/children/{ac['uid']}/arithmetic/facts?key={k}").text
    assert "Secure" in html
    assert "Last ordinary practice: 2026-03-03" in html
    assert "Ordinary first attempts so far: 3" in html      # the top-up is not counted
    assert html.count("<tr class=\"correct\">") == 3
    # A direction in the first rungs, never asked: not yet introduced
    unseen = next(x for x in FACT_ORDER if x not in ac["keys"])
    page = admin_client.get(f"/admin/children/{ac['uid']}/arithmetic/facts?key={unseen}").text
    assert "Not yet introduced" in page or "Locked" in page
    # A direction from a rung that is not unlocked
    late = "m:12x12"
    assert "Locked" in admin_client.get(
        f"/admin/children/{ac['uid']}/arithmetic/facts?key={late}").text
    assert admin_client.get(
        f"/admin/children/{ac['uid']}/arithmetic/facts?key=bogus").status_code == 404


def test_arithmetic_item_needing_review_and_focus(admin_client, arith_child):
    ac = arith_child
    html = admin_client.get(f"/admin/children/{ac['uid']}/arithmetic/facts?key={ac['keys'][0]}").text
    assert "Needing review" in html                          # [0, 1, 1]
    with app_db() as db:
        db.execute("DELETE FROM arithmetic_focus WHERE user_id=?", (ac["uid"],))
        db.execute(
            """INSERT INTO arithmetic_focus (user_id, family_key, started_at, after_attempt_id)
               VALUES (?, 'f:2x5', 'x', 0)""", (ac["uid"],))
    focus = admin_client.get(f"/admin/children/{ac['uid']}/arithmetic/facts?key=m:2x5").text
    assert "Current focus" in focus


# ── Overview ───────────────────────────────────────────────────────────────

def test_overview_summary(admin_client, spelling_child, arith_child):
    html = admin_client.get("/admin/progress").text
    assert "Sam" in html and "Ari" in html
    assert f"/admin/children/{spelling_child['uid']}/spelling" in html
    assert f"/admin/children/{arith_child['uid']}/arithmetic" in html
    with app_db() as db:
        s = pm.subject_summary(db, spelling_child["uid"], "spelling")
        a = pm.subject_summary(db, arith_child["uid"], "arithmetic")
    assert (s["practices"], s["secure"], s["review"], s["last_date"]) == (4, 9, 1, "2026-03-04")
    assert (a["practices"], a["secure"], a["last_date"]) == (3, 8, "2026-03-03")
    assert s["recent"] == 0                                   # March 2026 is not within 7 days of now


def test_overview_recent_count(admin_client):
    from datetime import datetime, timedelta, timezone
    uid = make_child("Rae")
    _, ids = setup_practice_list(uid, WORDS)
    now = datetime.now(timezone.utc)
    with app_db() as db:
        for days_ago in (1, 2, 30):
            ts = (now - timedelta(days=days_ago)).isoformat()
            sid = db.execute(
                """INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score, subject)
                   VALUES (?,?,NULL,10,20,'spelling')""", (ts, uid)).lastrowid
            for wid in ids.values():
                db.execute(
                    """INSERT INTO spelling_attempts
                       (timestamp, user_id, word_id, correct, attempt_number, session_id)
                       VALUES (?,?,?,1,1,?)""", (ts, uid, wid, sid))
        s = pm.subject_summary(db, uid, "spelling")
    assert s["practices"] == 3 and s["recent"] == 2


# ── Empty states and one point ─────────────────────────────────────────────

def test_empty_child_pages(admin_client):
    uid = make_child("Newbie")
    ov = admin_client.get("/admin/progress")
    assert ov.status_code == 200 and "Newbie" in ov.text and "None yet" in ov.text
    sp = admin_client.get(f"/admin/children/{uid}/spelling")
    assert sp.status_code == 200
    assert "No completed practices yet" in sp.text and "No practices yet." in sp.text
    assert "Nothing seen yet." in sp.text
    ar = admin_client.get(f"/admin/children/{uid}/arithmetic")
    assert ar.status_code == 200
    assert "No completed practices yet" in ar.text
    flat = " ".join(ar.text.split())
    assert "No tables unlocked yet" in flat and "Current focus family: none" in flat


def test_overview_with_no_children(admin_client):
    assert "No children yet." in admin_client.get("/admin/progress").text


def test_single_point_chart(admin_client):
    uid = make_child("One")
    _, ids = setup_practice_list(uid, WORDS)
    with app_db() as db:
        sid = add_session(db, uid, 1, "spelling")
        for wid in ids.values():
            add_spelling(db, uid, sid, wid, 1, 1, 1)
    d = chart_data(admin_client.get(f"/admin/children/{uid}/spelling").text)
    assert d["accuracy"] == [100.0] and d["secure"] == [0] and d["review"] == [10]


def test_unknown_child_is_404(admin_client):
    for path in ("spelling", "arithmetic", "spelling/practices/1", "arithmetic/practices/1",
                 "spelling/words/1", "arithmetic/facts?key=m:2x3"):
        assert admin_client.get(f"/admin/children/9999/{path}").status_code == 404


def test_chart_json_is_escaped(admin_client):
    """Item text never reaches the JSON, and tojson escapes angle brackets anyway."""
    uid = make_child("Esc")
    html = admin_client.get(f"/admin/children/{uid}/spelling").text
    assert "</script><script>" not in html


# ── Access control ─────────────────────────────────────────────────────────

NEW_PATHS = [
    "/admin/progress",
    "/admin/children/1/spelling",
    "/admin/children/1/arithmetic",
    "/admin/children/1/spelling/practices/1",
    "/admin/children/1/arithmetic/practices/1",
    "/admin/children/1/spelling/words/1",
    "/admin/children/1/arithmetic/facts?key=m:2x3",
]


@pytest.mark.parametrize("path", NEW_PATHS)
def test_child_cannot_open_admin_progress_pages(child_client, path):
    resp = child_client.get(path, follow_redirects=False)
    assert resp.status_code in (307, 403)
    assert resp.status_code == 403 or resp.headers["location"] == "/login"


@pytest.mark.parametrize("path", NEW_PATHS)
def test_anonymous_cannot_open_admin_progress_pages(client, path):
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (307, 403)
    assert resp.status_code == 403 or resp.headers["location"] == "/login"


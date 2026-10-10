"""End-to-end times-tables practice through the HTTP layer."""
import html as html_lib
import re

from services.arithmetic_facts import (
    FACT_ORDER, division_alt_text, division_clue_svg, division_clue_text, get_fact,
    multiplication_clue_lines,
)
from tests.conftest import app_db, extract_csrf, run_full_test, setup_practice_list

START = "/arithmetic/start"
SPELLING_WORDS = [f"word{c}x" for c in "abcdefghijkl"]


# ── Helpers ────────────────────────────────────────────────────────────────

def page_info(resp):
    key = re.search(r'name="fact_key" value="([^"]+)"', resp.text)
    attempt = re.search(r'id="arith-root" data-attempt="(\d)"', resp.text)
    assert key and attempt, resp.text[:500]
    return key.group(1), int(attempt.group(1))


def current(client):
    resp = client.get("/arithmetic/question")
    assert resp.status_code == 200
    key, attempt = page_info(resp)
    return key, attempt, resp


def answer(client, key, value, ms=None):
    data = {"fact_key": key, "answer": str(value)}
    if ms is not None:
        data["response_ms"] = str(ms)
    return client.post("/arithmetic/question", data=data, follow_redirects=False)


def card_text(html):
    """Visible text of the question card only."""
    card = re.search(r'<div id="question-card".*?</form>', html, flags=re.S).group(0)
    card = card.split("</form>")[0]
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", card)))


def play(client, fn):
    """Drive questions until the top-up offer. fn(fact, attempt) returns the
    answer to give, or None to give the right answer."""
    client.get(START)
    for _ in range(80):
        resp = client.get("/arithmetic/question", follow_redirects=False)
        if resp.status_code == 303:
            loc = resp.headers["location"]
            if loc.endswith("/feedback"):
                fb = client.get(loc)
                assert "Let's keep practising!" in fb.text
                continue_resp = client.get("/arithmetic/question?continue=1", follow_redirects=False)
                if continue_resp.status_code == 303:
                    assert continue_resp.headers["location"].endswith("/topup")
                    return
                key, attempt = page_info(continue_resp)
            else:
                assert loc.endswith("/topup"), loc
                return
        else:
            key, attempt = page_info(resp)
        fact = get_fact(key)
        value = fn(fact, attempt)
        answer(client, key, fact.answer if value is None else value)
    raise AssertionError("practice never finished")


def finish(client):
    return client.get("/arithmetic/results")


def session_row():
    with app_db() as db:
        return db.execute("SELECT * FROM test_sessions ORDER BY id DESC LIMIT 1").fetchone()


def attempts(**where):
    sql = "SELECT * FROM arithmetic_attempts"
    if where:
        sql += " WHERE " + " AND ".join(f"{k}=?" for k in where)
    with app_db() as db:
        return db.execute(sql + " ORDER BY id", tuple(where.values())).fetchall()


def right(fact, attempt):
    return None


def wrong_first_right_second(fact, attempt):
    return fact.answer + 1 if attempt == 1 else None


# ── Starting ───────────────────────────────────────────────────────────────

def test_start_creates_an_arithmetic_session_and_shows_first_question(child_client):
    resp = child_client.get(START, follow_redirects=False)
    assert resp.headers["location"] == "/arithmetic/question"
    s = session_row()
    assert s["subject"] == "arithmetic" and s["list_id"] is None
    assert s["score"] == 0 and s["max_score"] == 20
    key, attempt, page = current(child_client)
    assert attempt == 1
    assert "Practice 1 of 10" in page.text
    assert "New fact!" in page.text            # every baseline fact is new
    visible = re.sub(r"<script.*?</script>", "", page.text, flags=re.S)
    assert not re.search(r"\btest\b", re.sub(r"<[^>]+>", " ", visible), flags=re.I)


def test_question_redirects_to_dashboard_without_a_session(child_client):
    resp = child_client.get("/arithmetic/question", follow_redirects=False)
    assert resp.headers["location"] == "/child/dashboard"


def test_ten_segment_progress(child_client):
    child_client.get(START)
    key, _, page = current(child_client)
    assert len(re.findall(r'class="practice-segment( |")', page.text)) == 10
    answer(child_client, key, get_fact(key).answer)
    _, _, page = current(child_client)
    assert "Practice 2 of 10" in page.text
    assert len(re.findall(r'class="practice-segment is-done"', page.text)) == 1
    assert "New fact!" in page.text


def test_requires_login(client):
    resp = client.get(START, follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert resp.headers["location"].startswith("/login")


def test_non_numeric_answer_does_not_use_up_an_attempt(child_client):
    child_client.get(START)
    key, _, _ = current(child_client)
    resp = answer(child_client, key, "abc")
    assert resp.headers["location"] == "/arithmetic/question"
    assert attempts() == []
    _, attempt, _ = current(child_client)
    assert attempt == 1


def test_stale_fact_key_is_ignored(child_client):
    child_client.get(START)
    key, _, _ = current(child_client)
    other = next(k for k in FACT_ORDER if k != key)
    answer(child_client, other, get_fact(other).answer)
    assert attempts() == []


# ── Scoring and the second attempt ─────────────────────────────────────────

def test_first_try_correct_scores_two_and_second_try_scores_one(child_client):
    child_client.get(START)
    key, _, _ = current(child_client)
    resp = answer(child_client, key, get_fact(key).answer)
    assert resp.headers["location"] == "/arithmetic/question?well_done=1"
    assert session_row()["score"] == 2

    key, _, _ = current(child_client)
    answer(child_client, key, get_fact(key).answer + 1)
    key2, attempt, _ = current(child_client)
    assert key2 == key and attempt == 2
    answer(child_client, key, get_fact(key).answer)
    assert session_row()["score"] == 3
    rows = attempts(fact_key=key)
    assert [(r["attempt_number"], r["correct"]) for r in rows] == [(1, 0), (2, 1)]


def test_wrong_twice_shows_completed_fact_then_moves_on(child_client):
    child_client.get(START)
    key, _, _ = current(child_client)
    fact = get_fact(key)
    answer(child_client, key, fact.answer + 1)
    resp = answer(child_client, key, fact.answer + 2)
    assert resp.headers["location"] == "/arithmetic/feedback"
    fb = child_client.get("/arithmetic/feedback")
    assert f"{fact.text} = {fact.answer}" in fb.text
    assert "Let's keep practising!" in fb.text
    # the question page sends the child to the feedback first, then moves on
    assert child_client.get("/arithmetic/question", follow_redirects=False).headers["location"] \
        == "/arithmetic/feedback"
    nxt = child_client.get("/arithmetic/question?continue=1")
    assert "Practice 2 of 10" in nxt.text
    assert session_row()["score"] == 0
    assert [r["attempt_number"] for r in attempts(fact_key=key)] == [1, 2]


# ── Clues ──────────────────────────────────────────────────────────────────



def test_multiplication_clue_counts_in_the_right_hand_factor(child_client):
    child_client.get(START)
    # find a multiplication question in the baseline queue
    for _ in range(10):
        key, _, page = current(child_client)
        fact = get_fact(key)
        if fact.kind == "m" and fact.left >= 3:
            break
        answer(child_client, key, fact.answer)
    else:
        raise AssertionError("no multiplication question")
    assert "= ?" in card_text(page.text)
    answer(child_client, key, fact.answer + 1)
    _, attempt, clue_page = current(child_client)
    assert attempt == 2
    text = card_text(clue_page.text)
    for k in range(1, fact.left):
        assert f"{k} × {fact.right} = {k * fact.right}" in text
    assert f"{fact.left} × {fact.right} = ?" in text
    assert f"= {fact.answer}" not in text
    assert f"Let's count in {fact.right}s" in text


def test_division_clue_page_has_exact_diagram_and_no_answer(child_client):
    child_client.get(START)
    for _ in range(10):
        key, _, page = current(child_client)
        fact = get_fact(key)
        if fact.kind == "d" and fact.answer not in (fact.left, fact.right):
            break
        answer(child_client, key, fact.answer)
    else:
        raise AssertionError("no suitable division question")
    answer(child_client, key, fact.answer + 1)
    _, attempt, clue_page = current(child_client)
    assert attempt == 2
    html = clue_page.text
    assert division_clue_text(fact) in html.replace("&#39;", "'")
    assert html.count('class="counter"') == fact.left
    assert html.count('class="group"') == fact.right
    assert f'aria-label="{division_alt_text(fact)}"' in html
    text = card_text(html)
    assert not re.search(rf"\b{fact.answer}\b", text)


def test_answer_is_absent_from_page_source_on_attempts_one_and_two(child_client):
    """Core integrity invariant, like spelling's: the child must not be able
    to read the answer from the page on either attempt."""
    child_client.get(START)
    seen_kinds = set()
    for _ in range(10):
        key, _, page1 = current(child_client)
        fact = get_fact(key)
        seen_kinds.add(fact.kind)
        for html in (page1.text,):
            text = card_text(html)
            assert not re.search(rf"\b{fact.answer}\b", text) or fact.answer in (fact.left, fact.right)
            assert f"= {fact.answer}" not in text
            assert f'value="{fact.answer}"' not in html
        answer(child_client, key, fact.answer + 1)
        _, attempt, page2 = current(child_client)
        assert attempt == 2
        text2 = card_text(page2.text)
        assert f"= {fact.answer}" not in text2
        if fact.answer not in (fact.left, fact.right):
            assert not re.search(rf"\b{fact.answer}\b", text2)
        answer(child_client, key, fact.answer)
    assert seen_kinds == {"m", "d"}


def test_clue_helpers_never_contain_the_answer_for_any_fact():
    import re as _re
    for fact in (get_fact(k) for k in FACT_ORDER):
        if fact.kind == "m":
            lines = multiplication_clue_lines(fact)
            assert len(lines) == fact.left
            assert lines[-1] == f"{fact.left} × {fact.right} = ?"
            assert all(_re.search(rf"= {fact.answer}$", ln) is None for ln in lines)
            assert [int(ln.split("= ")[1]) for ln in lines[:-1]] == [
                k * fact.right for k in range(1, fact.left)]
        else:
            svg = division_clue_svg(fact)
            assert svg.count('<circle class="counter"') == fact.left
            assert svg.count('<g class="group">') == fact.right
            groups = svg.split('<g class="group">')[1:]
            assert all(g.count('<circle class="counter"') == fact.answer for g in groups)
            assert svg.count("<rect") == fact.right
            alt = division_alt_text(fact)
            assert alt == f"{fact.left} counters in {fact.right} equal groups"
            assert f'aria-label="{alt}"' in svg
            assert "<image" not in svg and "href" not in svg


def test_topups_show_no_clue(child_client):
    run_two_practices(child_client, wrong_first_right_second)
    child_client.post("/arithmetic/topup")
    key, attempt, page = current(child_client)
    assert attempt == 1 and "count in" not in page.text and 'class="counter"' not in page.text
    assert "Bonus question" in page.text


# ── Top-ups ────────────────────────────────────────────────────────────────

def run_two_practices(client, fn):
    """A perfect baseline, then a second practice driven by fn, stopping at
    the top-up offer."""
    play(client, right)
    finish(client)
    play(client, fn)


def test_topups_revisit_first_try_misses_first_and_are_single_attempt(child_client):
    run_two_practices(child_client, wrong_first_right_second)
    missed = [r["fact_key"] for r in attempts() if r["attempt_number"] == 1 and r["correct"] == 0]
    assert len(missed) == 10
    sid = session_row()["id"]
    offer = child_client.get("/arithmetic/topup")
    assert offer.status_code == 200 and "Answer another question" in offer.text
    assert session_row()["score"] == 10      # 10 questions at one point each
    child_client.post("/arithmetic/topup")
    key, attempt, _ = current(child_client)
    assert attempt == 1
    assert key == [r["fact_key"] for r in attempts(session_id=sid)
                   if r["attempt_number"] == 1 and r["correct"] == 0][0]
    # wrong top-up: no clue, no second attempt, no point
    resp = answer(child_client, key, get_fact(key).answer + 1)
    assert resp.headers["location"] == "/arithmetic/topup?result=missed"
    assert session_row()["score"] == 10
    child_client.post("/arithmetic/topup")
    key2, _, _ = current(child_client)
    assert key2 != key
    resp = answer(child_client, key2, get_fact(key2).answer)
    assert resp.headers["location"] == "/arithmetic/topup?result=earned"
    assert session_row()["score"] == 11
    tops = [r for r in attempts(session_id=sid) if r["attempt_number"] == 3]
    assert [r["correct"] for r in tops] == [0, 1]


def test_topup_score_is_capped_at_twenty_and_ends_at_twenty(child_client):
    play(child_client, right)
    finish(child_client)
    play(child_client, right)
    # a perfect score is 20: no top-up is offered
    resp = child_client.get("/arithmetic/topup", follow_redirects=False)
    assert resp.headers["location"] == "/arithmetic/results"
    assert session_row()["score"] == 20


def test_topup_reaching_twenty_goes_to_results(child_client):
    play(child_client, right)
    finish(child_client)
    state = {"n": 0}

    def one_second_try(fact, attempt):
        state["n"] += 1
        return fact.answer + 1 if (state["n"] == 1 and attempt == 1) else None

    play(child_client, one_second_try)
    assert session_row()["score"] == 19
    child_client.post("/arithmetic/topup")
    key, _, _ = current(child_client)
    answer(child_client, key, get_fact(key).answer)
    assert session_row()["score"] == 20
    resp = child_client.get("/arithmetic/topup", follow_redirects=False)
    assert resp.headers["location"] == "/arithmetic/results"


def test_topups_never_change_evidence_focus_or_introduce_facts(child_client):
    play(child_client, right)
    finish(child_client)
    play(child_client, wrong_first_right_second)
    with app_db() as db:
        before_focus = [tuple(r) for r in db.execute("SELECT * FROM arithmetic_focus")]
        seen_before = {r["fact_key"] for r in db.execute(
            "SELECT fact_key FROM arithmetic_attempts WHERE attempt_number=1")}
        hist_before = [tuple(r) for r in db.execute(
            "SELECT fact_key, correct FROM arithmetic_attempts WHERE attempt_number=1")]
    for _ in range(3):
        child_client.post("/arithmetic/topup")
        key, _, _ = current(child_client)
        assert key in seen_before
        answer(child_client, key, get_fact(key).answer)
    with app_db() as db:
        assert [tuple(r) for r in db.execute("SELECT * FROM arithmetic_focus")] == before_focus
        assert [tuple(r) for r in db.execute(
            "SELECT fact_key, correct FROM arithmetic_attempts WHERE attempt_number=1")] == hist_before


# ── Response time ──────────────────────────────────────────────────────────

def test_client_response_time_is_recorded(child_client):
    child_client.get(START)
    key, _, _ = current(child_client)
    answer(child_client, key, get_fact(key).answer, ms=1234)
    assert attempts()[0]["response_ms"] == 1234


def test_response_time_falls_back_to_server_clock_when_missing_or_invalid(child_client):
    child_client.get(START)
    for bad in (None, "abc", "-5", ""):
        key, _, _ = current(child_client)
        answer(child_client, key, get_fact(key).answer, ms=bad if bad is not None else None)
    ms = [r["response_ms"] for r in attempts()]
    assert len(ms) == 4 and all(m is not None and 0 <= m < 5000 for m in ms)


def test_response_time_is_clamped(child_client):
    child_client.get(START)
    key, _, _ = current(child_client)
    answer(child_client, key, get_fact(key).answer, ms=99999999999)
    value = attempts()[0]["response_ms"]
    assert value is not None and value <= 600000 and value < 5000   # server clock limits it


# ── Evidence and focus through the routes ──────────────────────────────────

def test_ordinary_attempts_feed_the_next_practice_focus(child_client):
    play(child_client, right)
    finish(child_client)
    child_client.get(START)
    with app_db() as db:
        row = db.execute("SELECT family_key FROM arithmetic_focus WHERE completed_at IS NULL").fetchone()
    assert row["family_key"] == "f:2x5"


# ── Results and rewards ────────────────────────────────────────────────────

def test_results_show_badge_trophy_and_credit_but_no_answers(child_client):
    play(child_client, right)
    resp = finish(child_client)
    assert "Practice Complete" in resp.text
    assert "Times tables practice" in resp.text
    assert "Badge earned for today!" in resp.text
    assert "You've started the 2 and 10 times tables!" in resp.text
    assert "Trophy" not in resp.text      # starting is not a trophy any more
    assert "/arithmetic/start" in resp.text
    visible = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", resp.text, flags=re.S))
    assert "\u00d7" in visible or "\u00f7" in visible
    assert "=" not in visible          # questions are listed, answers are not


def test_game_credit_needs_ten_points_and_badge_needs_sixteen(child_client):
    def ten_points(fact, attempt):
        # first-try right for 5 questions (10 points), second try for none
        ten_points.n += 1
        return None if ten_points.n <= 5 else fact.answer + 1 + attempt

    ten_points.n = 0
    child_client.get(START)
    play(child_client, ten_points)
    resp = finish(child_client)
    assert session_row()["score"] == 10
    assert "Pick a game to play" in resp.text
    assert "Badge earned" not in resp.text


def test_below_ten_earns_no_game_credit(child_client):
    play(child_client, lambda f, a: f.answer + 1 + a)
    resp = finish(child_client)
    assert session_row()["score"] == 0
    assert "Pick a game to play" not in resp.text


def test_qualifying_practice_banks_one_server_side_game_play(child_client):
    play(child_client, right)
    resp = finish(child_client)
    with app_db() as db:
        credits = db.execute("SELECT score, status FROM user_game_credits").fetchall()
    assert [tuple(c) for c in credits] == [(20, "available")]
    assert 'action="/child/games/circles.html"' in resp.text

    token = extract_csrf(resp.text)
    game = child_client.post("/child/games/circles.html", data={"csrf_token": token})
    assert game.status_code == 200
    assert "var remaining = 120;" in game.text          # duration from the real score
    again = child_client.post("/child/games/circles.html", data={"csrf_token": token})
    assert again.status_code == 200 and "/mini-games/" not in again.text   # spent


def test_low_arithmetic_score_forfeits_an_unspent_game_play(child_client):
    play(child_client, right)
    finish(child_client)
    child_client.get(START)
    play(child_client, lambda f, a: f.answer + 1 + a)
    finish(child_client)
    with app_db() as db:
        statuses = [r["status"] for r in db.execute("SELECT status FROM user_game_credits")]
    assert statuses == ["forfeited"]


def count_badges():
    with app_db() as db:
        return db.execute("SELECT COUNT(*) AS c FROM test_badges").fetchone()["c"]


def test_arithmetic_badge_blocks_a_later_spelling_badge_the_same_day(child_client):
    play(child_client, right)
    assert "Badge earned" in finish(child_client).text
    setup_practice_list(child_client.child_id, SPELLING_WORDS)
    resp = run_full_test(child_client, lambda w: w)
    assert "Badge earned" not in resp.text
    assert count_badges() == 1


def test_spelling_badge_blocks_a_later_arithmetic_badge_the_same_day(child_client):
    setup_practice_list(child_client.child_id, SPELLING_WORDS)
    assert "Badge earned" in run_full_test(child_client, lambda w: w).text
    play(child_client, right)
    resp = finish(child_client)
    assert "Badge earned" not in resp.text
    assert count_badges() == 1
    assert session_row()["score"] == 20 and "Pick a game to play" in resp.text   # game time still earned


def test_every_third_badge_across_subjects_unlocks_a_game(child_client):
    with app_db() as db:
        for day in (1, 2):
            sid = db.execute(
                "INSERT INTO test_sessions (timestamp,user_id,list_id,score,max_score) VALUES (?,?,NULL,18,20)",
                (f"2025-01-0{day}T10:00:00+00:00", child_client.child_id),
            ).lastrowid
            db.execute("INSERT INTO test_badges (user_id,session_id,earned_at) VALUES (?,?,?)",
                       (child_client.child_id, sid, f"2025-01-0{day}T10:00:00+00:00"))
    play(child_client, right)
    resp = finish(child_client)
    assert count_badges() == 3
    assert "A new game is ready!" in resp.text


def seed_secure_baseline(child_id):
    """Ten baseline directions already secure (three correct first tries)."""
    from services import arithmetic_progression as ap
    with app_db() as db:
        sid = db.execute(
            "INSERT INTO test_sessions (timestamp,user_id,list_id,score,max_score,subject) "
            "VALUES ('2025-01-01T00:00:00+00:00',?,NULL,20,20,'arithmetic')", (child_id,)
        ).lastrowid
        for key in ap.baseline_keys():
            for _ in range(3):
                db.execute(
                    "INSERT INTO arithmetic_attempts (timestamp,user_id,fact_key,correct,"
                    "attempt_number,session_id) VALUES ('2025-01-01T00:00:00+00:00',?,?,1,1,?)",
                    (child_id, key, sid))


def test_medal_at_ten_facts_first_secured_only_once(child_client):
    seed_secure_baseline(child_client.child_id)
    play(child_client, right)
    resp = finish(child_client)
    assert "Medal earned: 10 facts mastered!" in resp.text
    with app_db() as db:
        n = db.execute("SELECT COUNT(*) FROM milestone_medals WHERE subject='arithmetic'").fetchone()[0]
        assert n == 1
    play(child_client, right)
    assert "Medal earned: 10 facts" not in finish(child_client).text


def test_trophy_is_awarded_once_even_for_a_wrong_first_attempt(child_client):
    play(child_client, wrong_first_right_second)
    resp = finish(child_client)
    assert "You've started the 2 and 10 times tables!" in resp.text
    play(child_client, right)
    assert "You've started" not in finish(child_client).text
    with app_db() as db:
        rows = db.execute("SELECT group_id FROM start_trophies WHERE subject='arithmetic'").fetchall()
    assert [r["group_id"] for r in rows] == [1]


def test_new_fact_label_only_at_first_appearance(child_client):
    play(child_client, right)
    finish(child_client)
    child_client.get(START)
    new_flags = {}
    for _ in range(10):
        key, _, page = current(child_client)
        new_flags[key] = "New fact!" in page.text
        answer(child_client, key, get_fact(key).answer)
    with app_db() as db:
        first_session = {r["fact_key"] for r in db.execute(
            "SELECT fact_key FROM arithmetic_attempts WHERE session_id=(SELECT MIN(id) FROM test_sessions)")}
    assert any(new_flags.values()) and not all(new_flags.values())
    assert all(not v for k, v in new_flags.items() if k in first_session)


# ── Dashboard and admin ────────────────────────────────────────────────────

def test_dashboard_offers_both_practices_and_shows_arithmetic_awards(child_client):
    seed_secure_baseline(child_client.child_id)
    play(child_client, right)
    finish(child_client)
    page = child_client.get("/child/dashboard").text
    assert "Start a spelling practice" in page and "Start a times tables practice" in page
    assert 'href="/arithmetic/start"' in page
    assert "10 facts mastered" in page
    assert "Started the 2 and 10 times tables" not in page   # start records are not shown
    assert "Times tables" in page            # in recent practices


def test_admin_child_detail_survives_arithmetic_sessions(admin_client, child_client):
    play(child_client, right)
    finish(child_client)
    admin_client.cookies.clear()
    from tests.conftest import TEST_PASSWORD, login
    login(admin_client, "admin", TEST_PASSWORD)
    resp = admin_client.get(f"/admin/children/{child_client.child_id}")
    assert resp.status_code == 200
    assert "Times tables" in resp.text
    assert admin_client.get("/admin/").status_code == 200

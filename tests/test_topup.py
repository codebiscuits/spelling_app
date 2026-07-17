"""Post-test top-up flow: bonus words earn +1 point each until 20 or stop."""

from tests.conftest import (
    app_db,
    current_word,
    setup_practice_list,
    submit_answer,
)


def get_session_row():
    with app_db() as db:
        return db.execute(
            "SELECT * FROM test_sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()


def finish_main_test(client, answer_fn):
    """Answer every main-test word, stopping at the top-up offer redirect."""
    client.get("/test/start")
    for _ in range(50):
        resp = client.get("/test/word", follow_redirects=False)
        if resp.status_code == 303:
            assert resp.headers["location"] == "/test/topup"
            return
        word_id, word, _ = current_word(client)
        submit_answer(client, word_id, answer_fn(word))
    raise AssertionError("Test never finished")


def accept_offer(client):
    resp = client.post("/test/topup", follow_redirects=False)
    assert resp.status_code == 303
    return resp


# ── Offer page ─────────────────────────────────────────────────────────────

def test_offer_page_shown_when_below_target(child_client):
    setup_practice_list(child_client.child_id, ["cat", "dog", "sun", "hat", "pig"])
    finish_main_test(child_client, lambda w: "xx" if w == "cat" else w)  # 8/20
    resp = child_client.get("/test/topup")
    assert resp.status_code == 200
    assert "Spell another word" in resp.text
    assert "8" in resp.text


def test_offer_skipped_when_nothing_left_to_ask(child_client):
    """All words right and no unasked words in the pool -> nothing to offer."""
    setup_practice_list(child_client.child_id, ["cat", "dog", "sun", "hat", "pig"])
    finish_main_test(child_client, lambda w: w)  # 10/20, pool exhausted
    resp = child_client.get("/test/topup", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/test/results"


def test_perfect_score_skips_offer(child_client):
    words = ["apple", "banana", "carrot", "dolphin", "eagle",
             "forest", "garden", "harbor", "island", "jungle"]
    setup_practice_list(child_client.child_id, words)
    finish_main_test(child_client, lambda w: w)  # 20/20
    resp = child_client.get("/test/topup", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/test/results"


def test_offer_redirects_to_word_mid_test(child_client):
    setup_practice_list(child_client.child_id, ["cat", "dog"])
    child_client.get("/test/start")
    resp = child_client.get("/test/topup", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/test/word"


# ── Bonus words ────────────────────────────────────────────────────────────

def test_missed_word_offered_first_and_earns_one_point(child_client):
    setup_practice_list(child_client.child_id, ["cat", "dog", "sun", "hat", "pig"])
    finish_main_test(child_client, lambda w: "xx" if w == "cat" else w)
    row = get_session_row()
    assert row["score"] == 8  # 4 words right first try

    accept_offer(child_client)
    word_id, word, resp = current_word(child_client)
    assert word == "cat"  # the missed word comes back first
    assert "Bonus word" in resp.text
    assert "cat" not in resp.text  # never revealed, same as attempt 1

    submit_answer(child_client, word_id, "cat")
    assert get_session_row()["score"] == 9

    with app_db() as db:
        att = db.execute(
            """SELECT attempt_number, correct FROM spelling_attempts
               WHERE session_id=? ORDER BY id DESC LIMIT 1""",
            (row["id"],),
        ).fetchone()
    assert att["attempt_number"] == 3
    assert att["correct"] == 1


def test_wrong_bonus_answer_scores_nothing(child_client):
    setup_practice_list(child_client.child_id, ["cat", "dog", "sun", "hat", "pig"])
    finish_main_test(child_client, lambda w: "xx" if w == "cat" else w)

    accept_offer(child_client)
    word_id, _, _ = current_word(child_client)
    resp = submit_answer(child_client, word_id, "wrong")
    assert resp.headers["location"] == "/test/topup?result=missed"
    assert get_session_row()["score"] == 8

    with app_db() as db:
        att = db.execute(
            """SELECT attempt_number, correct FROM spelling_attempts
               WHERE session_id=? ORDER BY id DESC LIMIT 1""",
            (get_session_row()["id"],),
        ).fetchone()
    assert att["attempt_number"] == 3
    assert att["correct"] == 0


def test_pool_words_after_missed_exhausted_then_cap_at_20(child_client):
    words = ["apple", "banana", "carrot", "dolphin", "eagle", "forest",
             "garden", "harbor", "island", "jungle", "kitten", "lantern"]
    setup_practice_list(child_client.child_id, words)

    state = {"target": None}

    def answer(w):
        if state["target"] is None:
            state["target"] = w
        return "xx" if w == state["target"] else w

    finish_main_test(child_client, answer)  # one word wrong twice -> 18/20
    sid = get_session_row()["id"]
    assert get_session_row()["score"] == 18

    # 1st bonus: the missed word
    accept_offer(child_client)
    wid, w, _ = current_word(child_client)
    assert w == state["target"]
    submit_answer(child_client, wid, w)
    assert get_session_row()["score"] == 19

    # 2nd bonus: a fresh word from the pool, never asked in the main phase
    accept_offer(child_client)
    wid2, w2, resp2 = current_word(child_client)
    assert "Bonus word" in resp2.text
    submit_answer(child_client, wid2, w2)
    assert get_session_row()["score"] == 20
    with app_db() as db:
        cnt = db.execute(
            "SELECT COUNT(*) AS c FROM spelling_attempts WHERE session_id=? AND word_id=?",
            (sid, wid2),
        ).fetchone()["c"]
    assert cnt == 1  # only the bonus attempt — not part of the main queue

    # At 20 the offer is over
    resp = child_client.get("/test/topup", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/test/results"


# ── Reward interactions ────────────────────────────────────────────────────

def test_bonus_correct_does_not_grant_first_try_mastery(child_client):
    """Re-spelling a missed word correctly as a bonus must not count as
    first-try correct for the medal/trophy ladder."""
    setup_practice_list(child_client.child_id, ["cat", "dog"])
    finish_main_test(child_client, lambda w: "xx")  # both words wrong twice

    for _ in range(2):  # redo both missed words correctly
        accept_offer(child_client)
        wid, w, _ = current_word(child_client)
        submit_answer(child_client, wid, w)
    assert get_session_row()["score"] == 2

    child_client.get("/test/results")
    with app_db() as db:
        medals = db.execute("SELECT COUNT(*) AS c FROM user_badges").fetchone()["c"]
    assert medals == 0


def test_topup_can_earn_the_star_badge(child_client):
    """A 14/20 test topped up to 16 earns the star (decided: persistence at
    spelling counts toward the badge)."""
    words = ["apple", "banana", "carrot", "dolphin", "eagle", "forest",
             "garden", "harbor", "island", "jungle", "kitten", "lantern"]
    setup_practice_list(child_client.child_id, words)

    state = {"targets": set()}

    def answer(w):
        if w in state["targets"]:
            return "xx"
        if len(state["targets"]) < 3:
            state["targets"].add(w)
            return "xx"
        return w

    finish_main_test(child_client, answer)  # 3 words wrong twice -> 14/20
    assert get_session_row()["score"] == 14

    for _ in range(2):  # top up to 16
        accept_offer(child_client)
        wid, w, _ = current_word(child_client)
        submit_answer(child_client, wid, w)
    assert get_session_row()["score"] == 16

    resp = child_client.get("/test/results")
    assert "Badge earned" in resp.text
    assert "Bonus" in resp.text  # attempts table labels bonus attempts
    with app_db() as db:
        stars = db.execute("SELECT COUNT(*) AS c FROM test_badges").fetchone()["c"]
    assert stars == 1

"""End-to-end spelling-test flow through the HTTP layer (gTTS faked)."""

from tests.conftest import (
    app_db,
    setup_practice_list,
    current_word,
    run_full_test,
    submit_answer,
)


def get_score(session_id=None):
    with app_db() as db:
        if session_id is None:
            row = db.execute(
                "SELECT * FROM test_sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM test_sessions WHERE id=?", (session_id,)
            ).fetchone()
    return row


# ── Starting a test ────────────────────────────────────────────────────────

def test_child_with_no_lists_is_given_the_earliest_list(child_client):
    resp = child_client.get("/test/start", follow_redirects=False)
    assert resp.headers["location"] == "/test/word"
    with app_db() as db:
        rows = db.execute(
            """SELECT wl.name FROM user_list_unlocks ul JOIN word_lists wl ON wl.id=ul.list_id
               WHERE ul.user_id=?""",
            (child_client.child_id,),
        ).fetchall()
    assert [r["name"] for r in rows] == ["Year 1\u20132"]


def test_start_redirects_to_dashboard_when_unlocked_list_is_empty(child_client):
    setup_practice_list(child_client.child_id, [])
    resp = child_client.get("/test/start", follow_redirects=False)
    assert resp.headers["location"] == "/child/dashboard"


def test_start_creates_session_and_redirects_to_word(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    resp = child_client.get("/test/start", follow_redirects=False)
    assert resp.headers["location"] == "/test/word"

    session = get_score()
    assert session["user_id"] == child_client.child_id
    assert session["list_id"] is None  # multi-list sessions have no single list
    assert session["score"] == 0
    assert session["max_score"] == 20


def test_word_page_redirects_to_dashboard_without_active_test(child_client):
    resp = child_client.get("/test/word", follow_redirects=False)
    assert resp.headers["location"] == "/child/dashboard"


# ── Attempt 1 page ─────────────────────────────────────────────────────────

def test_attempt_1_never_reveals_the_word(child_client):
    """Core integrity invariant: on attempt 1 the word must not appear
    anywhere in the page source, or a child could just read it."""
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, word, resp = current_word(child_client)
    assert word == "xylophone"
    assert "xylophone" not in resp.text  # includes the audio URL: hashed filenames
    assert 'id="play-btn"' in resp.text
    assert 'id="word-audio"' in resp.text


def test_attempt_1_shows_sentence_button_for_homophones(child_client):
    setup_practice_list(
        child_client.child_id, ["where"],
        sentences={"where": "Do you know where my bag is?"},
    )
    child_client.get("/test/start")
    _, _, resp = current_word(child_client)
    assert 'id="sentence-btn"' in resp.text
    assert "/static/audio/sentence_" in resp.text
    # Neither the sentence text nor any audio URL may reveal the word
    assert "where" not in resp.text.lower()


def test_attempt_1_without_sentence_has_no_sentence_button(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    _, _, resp = current_word(child_client)
    assert 'id="sentence-btn"' not in resp.text


def test_attempt_1_degrades_gracefully_when_tts_fails(child_client, monkeypatch):
    import services.tts as tts_module

    def broken_tts(*args, **kwargs):
        raise Exception("TTS down")

    monkeypatch.setattr(tts_module, "gTTS", broken_tts)
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    _, _, resp = current_word(child_client)
    assert resp.status_code == 200
    assert "Audio unavailable" in resp.text


# ── Answer submission and scoring ──────────────────────────────────────────

def test_correct_first_try_scores_two_points(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, word, _ = current_word(child_client)

    resp = submit_answer(child_client, word_id, word)
    assert resp.headers["location"] == "/test/word?well_done=1"
    assert get_score()["score"] == 2


def test_answer_comparison_ignores_case_and_whitespace(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, _, _ = current_word(child_client)

    resp = submit_answer(child_client, word_id, "  XyloPHONE  ")
    assert resp.headers["location"] == "/test/word?well_done=1"
    assert get_score()["score"] == 2


def test_wrong_first_try_gives_second_attempt_showing_word(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, _, _ = current_word(child_client)

    resp = submit_answer(child_client, word_id, "zylofone")
    assert resp.headers["location"] == "/test/word"  # no well_done banner

    _, _, resp = current_word(child_client)
    assert "Second chance!" in resp.text
    assert "xylophone" in resp.text  # word is shown for study on attempt 2
    assert 'id="play-btn"' not in resp.text


def test_correct_second_try_scores_one_point(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, word, _ = current_word(child_client)

    submit_answer(child_client, word_id, "wrong")
    submit_answer(child_client, word_id, word)
    assert get_score()["score"] == 1


def test_wrong_twice_scores_nothing_and_moves_on(child_client):
    setup_practice_list(child_client.child_id, ["xylophone", "quixotic"])
    child_client.get("/test/start")
    word_id, _, _ = current_word(child_client)

    submit_answer(child_client, word_id, "wrong")
    submit_answer(child_client, word_id, "wrong again")
    assert get_score()["score"] == 0

    next_id, _, resp = current_word(child_client)
    assert next_id != word_id
    assert "Practice 2 of 2" in resp.text


def test_attempts_are_recorded(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, word, _ = current_word(child_client)

    submit_answer(child_client, word_id, "wrong")
    submit_answer(child_client, word_id, word)

    with app_db() as db:
        rows = db.execute(
            "SELECT attempt_number, correct FROM spelling_attempts ORDER BY id"
        ).fetchall()
    assert [(r["attempt_number"], r["correct"]) for r in rows] == [(1, 0), (2, 1)]


def test_submit_without_active_test_redirects_to_dashboard(child_client):
    resp = submit_answer(child_client, 1, "anything")
    assert resp.headers["location"] == "/child/dashboard"


def test_submitting_wrong_word_id_is_rejected(child_client):
    """Regression: answers are only accepted for the word currently being
    asked — a crafted word_id must not record an attempt or score."""
    lid, word_ids = setup_practice_list(child_client.child_id, ["xylophone", "quixotic"])
    child_client.get("/test/start")
    word_id, _, _ = current_word(child_client)
    other_id = next(wid for wid in word_ids.values() if wid != word_id)

    with app_db() as db:
        other_word = db.execute("SELECT word FROM words WHERE id=?", (other_id,)).fetchone()["word"]

    resp = submit_answer(child_client, other_id, other_word)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/test/word"
    assert get_score()["score"] == 0
    with app_db() as db:
        count = db.execute("SELECT COUNT(*) AS c FROM spelling_attempts").fetchone()["c"]
    assert count == 0


def test_double_submission_not_scored_twice(child_client):
    """Re-posting the same form (double click / back button) must not
    double-score the word."""
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    word_id, word, _ = current_word(child_client)

    submit_answer(child_client, word_id, word)
    submit_answer(child_client, word_id, word)
    assert get_score()["score"] == 2


# ── Full test run and results ──────────────────────────────────────────────

def test_full_run_all_correct_shows_results(child_client):
    words = ["xylophone", "quixotic", "brindle"]
    setup_practice_list(child_client.child_id, words)

    resp = run_full_test(child_client, lambda w: w)
    assert resp.status_code == 200
    assert "Practice Complete!" in resp.text
    for word in words:
        assert word in resp.text  # attempts table lists every word
    assert get_score()["score"] == 6


def test_results_page_clears_test_and_is_not_revisitable(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    run_full_test(child_client, lambda w: w)

    resp = child_client.get("/test/results", follow_redirects=False)
    assert resp.headers["location"] == "/child/dashboard"


def test_results_hides_games_below_half_score(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    resp = run_full_test(child_client, lambda w: w)  # score 2 < 10
    assert "Pick a game" not in resp.text


def test_results_offers_games_at_half_score(child_client):
    """Score >= 10/20 unlocks the mini-game picker."""
    words = ["xylophone", "quixotic", "brindle", "flummox", "widget"]
    setup_practice_list(child_client.child_id, words)
    resp = run_full_test(child_client, lambda w: w)  # 5 words × 2 = 10
    assert get_score()["score"] == 10
    assert "Pick a game" in resp.text
    assert "/child/games/" in resp.text


def test_first_practice_earns_start_trophy_and_badge_but_no_medal_or_list_unlock(child_client):
    list_id, _ = setup_practice_list(
        child_client.child_id, [f"word{c}" for c in "abcdefghij"], year_group=1, name="Start"
    )

    resp = run_full_test(child_client, lambda w: w)
    assert "You&#39;ve started Start!" in resp.text or "You've started Start!" in resp.text
    assert "Trophy won" not in resp.text
    assert "Badge earned for today!" in resp.text
    assert "Medal earned" not in resp.text
    assert "words mastered" not in resp.text

    with app_db() as db:
        trophies = db.execute(
            "SELECT group_id, silent FROM start_trophies WHERE user_id=?", (child_client.child_id,)
        ).fetchall()
        old_awards = db.execute("SELECT COUNT(*) AS c FROM user_badges").fetchone()["c"]
    assert [(t["group_id"], t["silent"]) for t in trophies] == [(list_id, 0)]
    assert old_awards == 0  # the old award table is no longer written


def test_new_word_label_only_at_introduction(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"])
    child_client.get("/test/start")
    first = child_client.get("/test/word")
    assert "New word!" in first.text
    assert "xylophone" not in first.text
    # Finish this practice, then start another: the word is no longer new
    word_id, word, _ = current_word(child_client)
    submit_answer(child_client, word_id, word)
    child_client.get("/test/results")
    child_client.get("/test/start")
    again = child_client.get("/test/word")
    assert "New word!" not in again.text


def test_failed_run_awards_nothing(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"], year_group=1)

    resp = run_full_test(child_client, lambda w: "wrong")
    assert "Medal earned" not in resp.text
    assert "Badge earned" not in resp.text

    with app_db() as db:
        count = db.execute("SELECT COUNT(*) AS c FROM user_badges").fetchone()["c"]
    assert count == 0


def test_only_one_badge_per_day_but_every_practice_still_earns_game_time(child_client):
    setup_practice_list(child_client.child_id, [f"word{c}" for c in "abcdefghij"])
    first = run_full_test(child_client, lambda w: w)
    assert "Badge earned for today!" in first.text
    second = run_full_test(child_client, lambda w: w)
    assert "Badge earned for today!" not in second.text
    assert "Pick a game to play!" in second.text  # game time is unchanged
    with app_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS c FROM test_badges WHERE user_id=?", (child_client.child_id,)
        ).fetchone()["c"]
    assert count == 1


def test_tenth_mastered_word_earns_a_medal_banner_and_no_game(child_client):
    words = [f"word{c}" for c in "abcdefghij"]
    _, ids = setup_practice_list(child_client.child_id, words)
    with app_db() as db:
        sid = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',?,NULL,0,20)",
            (child_client.child_id,),
        ).lastrowid
        for w in words:
            for _ in range(2 if w == "worda" else 3):   # worda needs one more correct
                db.execute(
                    """INSERT INTO spelling_attempts
                       (timestamp, user_id, word_id, correct, attempt_number, session_id)
                       VALUES ('2025-01-01',?,?,1,1,?)""",
                    (child_client.child_id, ids[w], sid),
                )
    resp = run_full_test(child_client, lambda w: w)
    assert "Medal earned: 10 words mastered!" in resp.text
    assert "A new game is ready!" not in resp.text
    assert "You've started" in resp.text  # a list started with no earlier record
    with app_db() as db:
        games = db.execute(
            "SELECT source FROM user_game_unlocks WHERE user_id=?", (child_client.child_id,)
        ).fetchall()
    assert all(g["source"] != "medal" for g in games)


def test_silent_awards_show_no_banner(child_client):
    words = [f"word{c}" for c in "abcdefghij"]
    lid, ids = setup_practice_list(child_client.child_id, words)
    with app_db() as db:
        db.execute(
            "INSERT INTO start_trophies (user_id, subject, group_id, earned_at, silent) VALUES (?,?,?,?,1)",
            (child_client.child_id, "spelling", lid, "2025-01-01"),
        )
    resp = run_full_test(child_client, lambda w: w)
    assert "You've started" not in resp.text

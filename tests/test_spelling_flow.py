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

def test_start_redirects_to_dashboard_when_no_lists_unlocked(child_client):
    resp = child_client.get("/test/start", follow_redirects=False)
    assert resp.headers["location"] == "/child/dashboard"


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
    assert "Word 2 of 2" in resp.text


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
    assert "Test Complete!" in resp.text
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


def test_perfect_run_awards_medal_trophy_and_unlocks_next_year(child_client):
    """Mastering a year-1 list first try earns medal + trophy and unlocks
    the year-3 curriculum list."""
    setup_practice_list(child_client.child_id, ["xylophone"], year_group=1)

    resp = run_full_test(child_client, lambda w: w)
    assert "Medal earned!" in resp.text
    assert "Trophy earned!" in resp.text
    assert "unlocked!" in resp.text

    with app_db() as db:
        badge_types = {
            r["badge_type"] for r in db.execute(
                "SELECT badge_type FROM user_badges WHERE user_id=?",
                (child_client.child_id,),
            ).fetchall()
        }
        unlocked_year_groups = {
            r["year_group"] for r in db.execute(
                """SELECT wl.year_group FROM user_list_unlocks ul
                   JOIN word_lists wl ON wl.id=ul.list_id WHERE ul.user_id=?""",
                (child_client.child_id,),
            ).fetchall()
        }
    assert badge_types == {"medal", "trophy"}
    assert 3 in unlocked_year_groups  # seeded Year 3–4 curriculum list


def test_failed_run_awards_nothing(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"], year_group=1)

    resp = run_full_test(child_client, lambda w: "wrong")
    assert "Medal earned!" not in resp.text
    assert "Trophy earned!" not in resp.text

    with app_db() as db:
        count = db.execute("SELECT COUNT(*) AS c FROM user_badges").fetchone()["c"]
    assert count == 0

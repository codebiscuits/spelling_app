import pytest

from routers.child import play_duration
from tests.conftest import app_db, run_full_test, setup_practice_list

CREDIT_WORDS = ["apple", "banana", "carrot", "dolphin", "eagle",
                "forest", "garden", "harbor", "island", "jungle"]


def earn_game_credit(client, answer_fn=lambda w: w, words=CREDIT_WORDS):
    """Complete a real test session so the results flow banks (or, for a
    failing answer_fn, withholds) a game-play credit."""
    setup_practice_list(client.child_id, words)
    return run_full_test(client, answer_fn)


# ── Dashboard ──────────────────────────────────────────────────────────────

def test_dashboard_renders_for_new_child(child_client):
    resp = child_client.get("/child/dashboard")
    assert resp.status_code == 200
    assert "Alice" in resp.text


def test_dashboard_shows_unlocked_lists(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"], name="My Words")
    resp = child_client.get("/child/dashboard")
    assert "My Words" in resp.text


def test_dashboard_shows_words_practised_without_weak_or_stale_labels(child_client):
    lid, word_ids = setup_practice_list(
        child_client.child_id, ["aa", "bb", "cc", "dd"], name="My Words"
    )
    wids = list(word_ids.values())
    with app_db() as db:
        sid = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',?,NULL,0,20)",
            (child_client.child_id,),
        ).lastrowid
        for wid, correct in ((wids[0], 1), (wids[1], 0)):
            db.execute(
                """INSERT INTO spelling_attempts
                   (timestamp, user_id, word_id, correct, attempt_number, session_id)
                   VALUES ('2025-01-01',?,?,?,1,?)""",
                (child_client.child_id, wid, correct, sid),
            )
        # A top-up attempt does not count as practised
        db.execute(
            """INSERT INTO spelling_attempts
               (timestamp, user_id, word_id, correct, attempt_number, session_id)
               VALUES ('2025-01-01',?,?,1,3,?)""",
            (child_client.child_id, wids[2], sid),
        )

    resp = child_client.get("/child/dashboard")
    assert resp.status_code == 200
    assert "Words practised" in resp.text
    assert "2 of 4" in resp.text
    for banned in ("Mastered", "Practising", "weak", "stale", "secure", "rank", "behind"):
        assert banned.lower() not in resp.text.lower(), banned


def test_dashboard_shows_new_medals_and_trophies(child_client):
    lid, _ = setup_practice_list(child_client.child_id, ["aa"], name="My Words")
    with app_db() as db:
        db.execute(
            "INSERT INTO milestone_medals (user_id, subject, threshold, earned_at, silent) VALUES (?,?,?,?,1)",
            (child_client.child_id, "spelling", 10, "2025-01-01"),
        )
        db.execute(
            "INSERT INTO start_trophies (user_id, subject, group_id, earned_at, silent) VALUES (?,?,?,?,1)",
            (child_client.child_id, "spelling", lid, "2025-01-01"),
        )
    resp = child_client.get("/child/dashboard")
    assert "10 words mastered" in resp.text
    assert "Started My Words" in resp.text


def test_dashboard_lists_recent_sessions_as_mixed_practice(child_client):
    with app_db() as db:
        db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',?,NULL,12,20)",
            (child_client.child_id,),
        )
    resp = child_client.get("/child/dashboard")
    assert "Mixed practice" in resp.text
    assert "12" in resp.text


# ── Mini-game wrapper ──────────────────────────────────────────────────────

def test_game_page_renders_after_qualifying_test(child_client):
    earn_game_credit(child_client)  # 10 words all correct -> 20/20
    resp = child_client.get("/child/games/circles.html")
    assert resp.status_code == 200
    assert "/mini-games/circles.html" in resp.text
    assert "var remaining = 120;" in resp.text  # duration from the real score


def test_game_page_redirects_without_credit(child_client):
    resp = child_client.get("/child/games/circles.html", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/child/dashboard"


def test_game_credit_is_single_use(child_client):
    earn_game_credit(child_client)
    assert child_client.get("/child/games/circles.html").status_code == 200
    resp = child_client.get("/child/games/circles.html", follow_redirects=False)
    assert resp.status_code == 303


def test_failing_test_banks_no_credit(child_client):
    earn_game_credit(child_client, answer_fn=lambda w: "wrong")  # score 0
    resp = child_client.get("/child/games/circles.html", follow_redirects=False)
    assert resp.status_code == 303


def test_sub_threshold_test_forfeits_previous_credit(child_client):
    """An unspent credit does not survive a later failing session."""
    earn_game_credit(child_client)
    earn_game_credit(
        child_client, answer_fn=lambda w: "wrong",
        words=["kitten", "lantern", "meadow", "narwhal", "octopus"],
    )
    resp = child_client.get("/child/games/circles.html", follow_redirects=False)
    assert resp.status_code == 303


def test_game_page_404s_for_unknown_file(child_client):
    assert child_client.get("/child/games/evil.html").status_code == 404


def test_game_page_404s_for_path_traversal(child_client):
    resp = child_client.get("/child/games/..%2F..%2Fmain.py")
    assert resp.status_code == 404


@pytest.mark.parametrize("score,duration", [
    (0, 60),     # floor
    (10, 60),    # threshold score → minimum time
    (15, 90),
    (20, 120),   # perfect score → maximum time
    (99, 120),   # capped at 20
])
def test_play_duration_scales_with_score(score, duration):
    assert play_duration(score) == duration

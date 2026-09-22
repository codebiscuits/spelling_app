import re

import pytest

from routers.child import play_duration
from tests.conftest import (
    app_db,
    current_word,
    extract_csrf,
    run_full_test,
    setup_practice_list,
    submit_answer,
)

CREDIT_WORDS = ["apple", "banana", "carrot", "dolphin", "eagle",
                "forest", "garden", "harbor", "island", "jungle"]


def earn_game_credit(client, answer_fn=lambda w: w, words=CREDIT_WORDS):
    """Complete a real test session so the results flow banks (or, for a
    failing answer_fn, withholds) a game-play credit."""
    setup_practice_list(client.child_id, words)
    return run_full_test(client, answer_fn)


def qualifying_test_before_results(client):
    """Complete a 20/20 test but retain the signed cookie before results."""
    setup_practice_list(client.child_id, CREDIT_WORDS)
    client.get("/test/start")
    for _ in range(10):
        word_id, word, _ = current_word(client)
        submit_answer(client, word_id, word)
    assert client.get("/test/topup", follow_redirects=False).headers["location"] == "/test/results"
    return client.cookies.get("session")


def start_game(client, filename, follow_redirects=True):
    csrf_token = extract_csrf(client.get("/login").text)
    return client.post(
        f"/child/games/{filename}",
        data={"csrf_token": csrf_token},
        follow_redirects=follow_redirects,
    )


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

def test_results_shows_recent_games_and_hides_stale_games_under_all_games(child_client):
    """Only games played in the last 30 days are in the initial picker."""
    from datetime import datetime, timezone
    from templates_env import CLASSIC_GAMES

    recent_game = CLASSIC_GAMES[0]
    stale_game = CLASSIC_GAMES[1]
    with app_db() as db:
        db.execute(
            "INSERT INTO user_game_plays (user_id, game_file, played_at) VALUES (?,?,?)",
            (child_client.child_id, recent_game["file"], datetime.now(timezone.utc).isoformat()),
        )

    resp = earn_game_credit(child_client)  # 10 words all correct -> 20/20

    assert resp.status_code == 200
    assert '<details class="all-games">' in resp.text
    visible_games, all_games = resp.text.split('<details class="all-games">', 1)
    assert recent_game["name"] in visible_games
    assert stale_game["name"] not in visible_games
    assert "All games" in all_games
    assert stale_game["name"] in all_games


def test_starting_a_game_requires_a_csrf_protected_post(child_client):
    results = earn_game_credit(child_client)

    assert child_client.get("/child/games/circles.html").status_code == 405
    assert child_client.post("/child/games/circles.html", data={"csrf_token": "wrong"}).status_code == 403

    csrf_token = extract_csrf(results.text)
    response = child_client.post("/child/games/circles.html", data={"csrf_token": csrf_token})
    assert response.status_code == 200


def test_raw_game_file_requires_a_single_use_wrapped_game_launch(child_client):
    assert child_client.get("/mini-games/circles.html").status_code == 404

    earn_game_credit(child_client)
    wrapper = start_game(child_client, "circles.html")
    launch = re.search(r'/mini-games/circles.html\?launch=([^"&]+)', wrapper.text)
    assert launch, "Game wrapper must include a one-time launch capability"

    game_url = f"/mini-games/circles.html?launch={launch.group(1)}"
    assert child_client.get(game_url).status_code == 200
    assert child_client.get(game_url).status_code == 404


def test_game_page_renders_after_qualifying_test(child_client):
    earn_game_credit(child_client)  # 10 words all correct -> 20/20
    resp = start_game(child_client, "circles.html")
    assert resp.status_code == 200
    assert "/mini-games/circles.html" in resp.text
    assert "var remaining = 120;" in resp.text  # duration from the real score


def test_replayed_session_cannot_spend_a_game_credit_twice(child_client):
    results = earn_game_credit(child_client)
    csrf_token = extract_csrf(results.text)
    pre_play_session = child_client.cookies.get("session")

    first = child_client.post("/child/games/circles.html", data={"csrf_token": csrf_token})
    assert first.status_code == 200

    child_client.cookies.set("session", pre_play_session)
    replay = child_client.post(
        "/child/games/fireworks.html",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert replay.status_code == 303

    with app_db() as db:
        plays = db.execute(
            "SELECT game_file FROM user_game_plays WHERE user_id=? ORDER BY id",
            (child_client.child_id,),
        ).fetchall()
    assert [play["game_file"] for play in plays] == ["circles.html"]


def test_replaying_pre_results_cookie_cannot_remint_a_spent_credit(child_client):
    pre_results_session = qualifying_test_before_results(child_client)
    assert child_client.get("/test/results").status_code == 200
    assert start_game(child_client, "circles.html").status_code == 200

    child_client.cookies.set(
        "session", pre_results_session, domain="testserver.local", path="/"
    )
    replayed_results = child_client.get("/test/results")
    assert replayed_results.status_code == 200
    replay = child_client.post(
        "/child/games/fireworks.html",
        data={"csrf_token": extract_csrf(replayed_results.text)},
        follow_redirects=False,
    )
    assert replay.status_code == 303

    with app_db() as db:
        credits = db.execute(
            "SELECT session_id, status FROM user_game_credits WHERE user_id=?",
            (child_client.child_id,),
        ).fetchall()
    assert len(credits) == 1
    assert credits[0]["status"] == "consumed"


def test_starting_a_game_records_a_play_for_that_child(child_client):
    earn_game_credit(child_client)

    assert start_game(child_client, "circles.html").status_code == 200
    with app_db() as db:
        row = db.execute(
            """SELECT game_file FROM user_game_plays
               WHERE user_id=? ORDER BY id DESC LIMIT 1""",
            (child_client.child_id,),
        ).fetchone()

    assert row["game_file"] == "circles.html"


def test_game_page_redirects_without_credit(child_client):
    resp = start_game(child_client, "circles.html", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/child/dashboard"


def test_game_credit_is_single_use(child_client):
    earn_game_credit(child_client)
    assert start_game(child_client, "circles.html").status_code == 200
    resp = start_game(child_client, "circles.html", follow_redirects=False)
    assert resp.status_code == 303


def test_failing_test_banks_no_credit(child_client):
    earn_game_credit(child_client, answer_fn=lambda w: "wrong")  # score 0
    resp = start_game(child_client, "circles.html", follow_redirects=False)
    assert resp.status_code == 303


def test_sub_threshold_test_forfeits_previous_credit(child_client):
    """An unspent credit does not survive a later failing session."""
    earn_game_credit(child_client)
    earn_game_credit(
        child_client, answer_fn=lambda w: "wrong",
        words=["kitten", "lantern", "meadow", "narwhal", "octopus"],
    )
    resp = start_game(child_client, "circles.html", follow_redirects=False)
    assert resp.status_code == 303


def test_game_page_404s_for_unknown_file(child_client):
    assert start_game(child_client, "evil.html").status_code == 404


def test_game_page_404s_for_path_traversal(child_client):
    resp = start_game(child_client, "..%2F..%2Fmain.py")
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

import pytest

from tests.conftest import app_db, setup_practice_list


# ── Dashboard ──────────────────────────────────────────────────────────────

def test_dashboard_renders_for_new_child(child_client):
    resp = child_client.get("/child/dashboard")
    assert resp.status_code == 200
    assert "Alice" in resp.text


def test_dashboard_shows_unlocked_lists(child_client):
    setup_practice_list(child_client.child_id, ["xylophone"], name="My Words")
    resp = child_client.get("/child/dashboard")
    assert "My Words" in resp.text


def test_dashboard_progress_counts(child_client):
    """Progress splits words into first-try / second-try / practising / new."""
    lid, word_ids = setup_practice_list(
        child_client.child_id, ["aa", "bb", "cc", "dd"], name="My Words"
    )
    wids = list(word_ids.values())
    with app_db() as db:
        sid = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',?,NULL,0,20)",
            (child_client.child_id,),
        ).lastrowid

        def attempt(wid, number, correct):
            db.execute(
                """INSERT INTO spelling_attempts
                   (timestamp, user_id, word_id, correct, attempt_number, session_id)
                   VALUES ('2025-01-01',?,?,?,?,?)""",
                (child_client.child_id, wid, correct, number, sid),
            )

        attempt(wids[0], 1, 1)              # first-try correct
        attempt(wids[1], 1, 0)
        attempt(wids[1], 2, 1)              # second-try correct
        attempt(wids[2], 1, 0)
        attempt(wids[2], 2, 0)              # attempted, never correct
        # wids[3] never attempted

    resp = child_client.get("/child/dashboard")
    assert resp.status_code == 200

    # 1/4 first-try = 25% mastered bar, 1/4 second-try = 25% practising bar
    assert 'class="progress-first" style="width:25%"' in resp.text
    assert 'class="progress-second" style="width:25%"' in resp.text
    # Total 4, Mastered 1, Practising 2 (attempted but not first-try), New 1
    stats = resp.text.split('class="word-stats"')[1].split("</div>")[0]
    values = [v.split("<")[0] for v in stats.split('<span class="stat-value">')[1:]]
    assert values == ["4", "1", "2", "1"]


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

def test_game_page_renders_known_game(child_client):
    resp = child_client.get("/child/games/circles.html")
    assert resp.status_code == 200
    assert "/mini-games/circles.html" in resp.text


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
def test_game_duration_scales_with_score(child_client, score, duration):
    resp = child_client.get(f"/child/games/circles.html?score={score}")
    assert f"var remaining = {duration};" in resp.text

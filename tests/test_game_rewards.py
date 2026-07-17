from database import init_db
from services.game_rewards import (
    BADGE_STEP,
    badges_until_next,
    check_and_unlock,
    next_locked,
    unlocked_files,
)
from templates_env import CLASSIC_GAMES, REWARD_GAMES
from tests.conftest import (
    app_db,
    current_word,
    extract_csrf,
    make_list,
    make_session,
    make_user,
    setup_practice_list,
    submit_answer,
)


def award(badge=False, medal=False, trophy=False):
    return {
        "badge_awarded": badge,
        "medal_awarded": medal,
        "trophy_awarded": trophy,
        "lists_unlocked": [],
    }


def give_badges(db, uid, lid, n):
    """Insert n test_badges rows for uid, simulating n prior badge-awarding
    sessions (as check_and_award would have already done)."""
    for _ in range(n):
        sid = make_session(db, uid, lid, score=16)
        db.execute(
            "INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)",
            (uid, sid, "2025-01-01T00:00:00+00:00"),
        )
    db.commit()


def unlock_game_for(child_id, filename, source="admin"):
    with app_db() as db:
        db.execute(
            """INSERT OR IGNORE INTO user_game_unlocks
               (user_id, game_file, earned_at, source) VALUES (?,?,?,?)""",
            (child_id, filename, "2025-01-01T00:00:00+00:00", source),
        )


# ── 1. Ladder ────────────────────────────────────────────────────────────────

def test_third_badge_unlocks_first_game(db):
    uid = make_user(db)
    lid = make_list(db)
    give_badges(db, uid, lid, BADGE_STEP)  # 3rd badge already recorded
    result = check_and_unlock(uid, award(badge=True), db)
    assert result is not None
    assert result["file"] == REWARD_GAMES[0]["file"]
    assert unlocked_files(uid, db) == {REWARD_GAMES[0]["file"]}


def test_sixth_badge_unlocks_second_game(db):
    uid = make_user(db)
    lid = make_list(db)
    give_badges(db, uid, lid, 6)  # 6th badge already recorded
    db.execute(
        """INSERT INTO user_game_unlocks (user_id, game_file, earned_at, source)
           VALUES (?,?,?,?)""",
        (uid, REWARD_GAMES[0]["file"], "2025-01-01T00:00:00+00:00", "badge"),
    )
    db.commit()
    result = check_and_unlock(uid, award(badge=True), db)
    assert result is not None
    assert result["file"] == REWARD_GAMES[1]["file"]


def test_medal_unlocks_immediately(db):
    uid = make_user(db)
    result = check_and_unlock(uid, award(medal=True), db)
    assert result is not None
    assert result["file"] == REWARD_GAMES[0]["file"]


def test_trophy_unlocks_immediately(db):
    uid = make_user(db)
    result = check_and_unlock(uid, award(trophy=True), db)
    assert result is not None
    assert result["file"] == REWARD_GAMES[0]["file"]


def test_badge_one_alone_unlocks_nothing(db):
    uid = make_user(db)
    lid = make_list(db)
    give_badges(db, uid, lid, 1)
    assert check_and_unlock(uid, award(badge=True), db) is None
    assert unlocked_files(uid, db) == set()


def test_badge_two_alone_unlocks_nothing(db):
    uid = make_user(db)
    lid = make_list(db)
    give_badges(db, uid, lid, 2)
    assert check_and_unlock(uid, award(badge=True), db) is None
    assert unlocked_files(uid, db) == set()


# ── 2. One-per-session cap ──────────────────────────────────────────────────

def test_trophy_and_medal_same_session_yields_one_unlock(db):
    uid = make_user(db)
    result = check_and_unlock(uid, award(medal=True, trophy=True), db)
    assert result is not None
    assert result["file"] == REWARD_GAMES[0]["file"]
    assert len(unlocked_files(uid, db)) == 1


# ── 3. Order & exhaustion ────────────────────────────────────────────────────

def test_unlocks_follow_release_order_then_exhaust(db):
    uid = make_user(db)
    sequence = []
    for _ in range(len(REWARD_GAMES)):
        result = check_and_unlock(uid, award(trophy=True), db)
        assert result is not None
        sequence.append(result["file"])
    assert sequence == [g["file"] for g in REWARD_GAMES]
    assert next_locked(uid, db) is None
    # Exhausted: further sessions no-op
    assert check_and_unlock(uid, award(trophy=True), db) is None
    assert unlocked_files(uid, db) == {g["file"] for g in REWARD_GAMES}


# ── 4. Route guards ──────────────────────────────────────────────────────────

def test_locked_reward_game_404s_on_both_routes(child_client):
    locked_file = REWARD_GAMES[-1]["file"]
    resp = child_client.get(f"/child/games/{locked_file}")
    assert resp.status_code == 404
    resp2 = child_client.get(f"/mini-games/{locked_file}")
    assert resp2.status_code == 404


def test_unlocked_reward_game_200s_on_both_routes(child_client):
    game_file = REWARD_GAMES[0]["file"]
    unlock_game_for(child_client.child_id, game_file)
    resp = child_client.get(f"/child/games/{game_file}")
    assert resp.status_code == 200
    resp2 = child_client.get(f"/mini-games/{game_file}")
    assert resp2.status_code == 200


def test_classic_games_always_200_for_child(child_client):
    classic_file = CLASSIC_GAMES[0]["file"]
    resp = child_client.get(f"/child/games/{classic_file}")
    assert resp.status_code == 200
    resp2 = child_client.get(f"/mini-games/{classic_file}")
    assert resp2.status_code == 200


def test_admin_can_fetch_any_reward_file(admin_client):
    locked_file = REWARD_GAMES[-1]["file"]
    resp = admin_client.get(f"/mini-games/{locked_file}")
    assert resp.status_code == 200


# ── 7. Launch gift ───────────────────────────────────────────────────────────

def test_launch_gift_grants_first_game_on_restart(client):
    with app_db() as db:
        cur = db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            ("Bob", "2016-01-01", "hash", "2025-01-01T00:00:00+00:00"),
        )
        bob_id = cur.lastrowid

    # Simulate an app restart: init_db() re-runs the launch-gift migration
    # for any child that still has zero unlock rows.
    init_db()

    with app_db() as db:
        rows = db.execute(
            "SELECT game_file, source FROM user_game_unlocks WHERE user_id=?", (bob_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["game_file"] == REWARD_GAMES[0]["file"]
    assert rows[0]["source"] == "launch"


# ── 5. Admin toggle (unlock/re-lock) ─────────────────────────────────────────

# A generously-sized word list: even a perfect 10/10 session keeps the
# cumulative first-try ratio for the *medal* rule (>=50% of the whole list)
# comfortably below threshold, so these results-page tests exercise the
# badge ladder in isolation without an incidental medal also firing.
PRACTICE_WORDS = [
    "apple", "banana", "carrot", "dolphin", "eagle",
    "forest", "garden", "harbor", "island", "jungle", "kitten", "lantern",
    "meadow", "narwhal", "octopus", "penguin", "quartz", "rabbit",
    "sunset", "turtle", "umbrella", "violet", "walnut", "xylophone",
]


def create_plain_child(name="Charlie"):
    with app_db() as db:
        cur = db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            (name, "2016-01-01", "hash", "2025-01-01T00:00:00+00:00"),
        )
        return cur.lastrowid


def test_admin_toggle_unlock_then_relock_round_trip(admin_client):
    child_id = create_plain_child()
    game_file = REWARD_GAMES[0]["file"]

    detail = admin_client.get(f"/admin/children/{child_id}")
    assert detail.status_code == 200
    csrf = extract_csrf(detail.text)
    resp = admin_client.post(
        f"/admin/children/{child_id}/games/{game_file}/toggle",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    with app_db() as db:
        row = db.execute(
            "SELECT source FROM user_game_unlocks WHERE user_id=? AND game_file=?",
            (child_id, game_file),
        ).fetchone()
    assert row is not None
    assert row["source"] == "admin"

    # Toggle again -> re-lock
    detail2 = admin_client.get(f"/admin/children/{child_id}")
    csrf2 = extract_csrf(detail2.text)
    resp2 = admin_client.post(
        f"/admin/children/{child_id}/games/{game_file}/toggle",
        data={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert resp2.status_code == 303
    with app_db() as db:
        row2 = db.execute(
            "SELECT 1 FROM user_game_unlocks WHERE user_id=? AND game_file=?",
            (child_id, game_file),
        ).fetchone()
    assert row2 is None


def test_admin_toggle_requires_csrf(admin_client):
    child_id = create_plain_child()
    game_file = REWARD_GAMES[0]["file"]
    resp = admin_client.post(
        f"/admin/children/{child_id}/games/{game_file}/toggle",
        data={"csrf_token": "wrong-token"},
    )
    assert resp.status_code == 403
    with app_db() as db:
        row = db.execute(
            "SELECT 1 FROM user_game_unlocks WHERE user_id=? AND game_file=?",
            (child_id, game_file),
        ).fetchone()
    assert row is None


def test_admin_toggle_invalid_filename_404s(admin_client):
    child_id = create_plain_child()
    detail = admin_client.get(f"/admin/children/{child_id}")
    csrf = extract_csrf(detail.text)
    resp = admin_client.post(
        f"/admin/children/{child_id}/games/not_a_real_game.html/toggle",
        data={"csrf_token": csrf},
    )
    assert resp.status_code == 404


# ── 6. Results page context (mystery hint, celebration, no leaks) ───────────

def run_full_session(client):
    """Drive one complete 10-word test session via the real HTTP flow,
    answering every word correctly on the first attempt (score 20/20),
    and return the GET /test/results response."""
    client.get("/test/start", follow_redirects=False)
    for _ in range(10):
        word_id, word, _ = current_word(client)
        submit_answer(client, word_id, word)
    return client.get("/test/results")


def test_mystery_hint_correct_after_first_badge(child_client):
    child_id = child_client.child_id
    setup_practice_list(child_id, PRACTICE_WORDS)
    resp = run_full_session(child_client)
    assert resp.status_code == 200
    assert "2 more" in resp.text


def test_mystery_hint_correct_after_second_badge(child_client):
    child_id = child_client.child_id
    list_id, _ = setup_practice_list(child_id, PRACTICE_WORDS)
    with app_db() as db:
        give_badges(db, child_id, list_id, 1)
    resp = run_full_session(child_client)
    assert resp.status_code == 200
    assert "1 more" in resp.text


def test_celebration_card_present_on_unlocking_session(child_client):
    child_id = child_client.child_id
    list_id, _ = setup_practice_list(child_id, PRACTICE_WORDS)
    with app_db() as db:
        give_badges(db, child_id, list_id, 2)
    resp = run_full_session(child_client)
    assert resp.status_code == 200
    game = REWARD_GAMES[0]
    assert "New game unlocked" in resp.text
    assert game["name"] in resp.text
    assert game["description"] in resp.text


def test_qualifying_multi_list_session_awards_exactly_one_badge(child_client):
    """Regression: the badge used to be inserted once per list touched by the
    session, so a 20/20 session drawing words from several lists inflated the
    lifetime star count and fired the every-3-stars game unlock early."""
    child_id = child_client.child_id
    setup_practice_list(child_id, ["apple", "banana", "carrot", "dolphin", "eagle"],
                        name="List A")
    setup_practice_list(child_id, ["forest", "garden", "harbor", "island", "jungle"],
                        name="List B")
    resp = run_full_session(child_client)  # 10 words -> both lists touched
    assert resp.status_code == 200
    with app_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS c FROM test_badges WHERE user_id=?", (child_id,)
        ).fetchone()["c"]
    assert count == 1


def test_locked_reward_game_names_never_leak_on_results_page(child_client):
    child_id = child_client.child_id
    setup_practice_list(child_id, PRACTICE_WORDS)
    # Only one badge this session (score 20/20, badge count 1 is not a
    # multiple of BADGE_STEP) -> no unlock, so every reward game stays locked.
    resp = run_full_session(child_client)
    assert resp.status_code == 200
    for g in REWARD_GAMES:
        assert g["name"] not in resp.text
        assert g["description"] not in resp.text

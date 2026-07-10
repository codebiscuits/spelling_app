from auth import verify_password
from tests.conftest import app_db, get_csrf


def post(client, url, data, csrf_page="/admin/"):
    data = {**data, "csrf_token": get_csrf(client, csrf_page)}
    return client.post(url, data=data, follow_redirects=False)


def make_child(name="Bobby"):
    with app_db() as db:
        cur = db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            (name, "2016-01-01", "hash", "2025-01-01T00:00:00+00:00"),
        )
        return cur.lastrowid


# ── Dashboard ──────────────────────────────────────────────────────────────

def test_dashboard_lists_seeded_curriculum_and_children(admin_client):
    make_child("Bobby")
    resp = admin_client.get("/admin/")
    assert resp.status_code == 200
    assert "Year 1–2" in resp.text
    assert "Bobby" in resp.text


# ── Word list CRUD ─────────────────────────────────────────────────────────

def test_create_word_list(admin_client):
    resp = post(admin_client, "/admin/lists/create",
                {"name": "  My List  ", "year_group": "3"}, csrf_page="/admin/lists")
    assert resp.status_code == 303
    with app_db() as db:
        row = db.execute("SELECT * FROM word_lists WHERE name='My List'").fetchone()
    assert row["year_group"] == 3


def test_create_word_list_without_year_group(admin_client):
    post(admin_client, "/admin/lists/create",
         {"name": "No Year", "year_group": ""}, csrf_page="/admin/lists")
    with app_db() as db:
        row = db.execute("SELECT * FROM word_lists WHERE name='No Year'").fetchone()
    assert row["year_group"] is None


def test_create_word_list_with_junk_year_group_does_not_crash(admin_client):
    """Regression: non-numeric year group used to raise an unhandled 500."""
    resp = post(admin_client, "/admin/lists/create",
                {"name": "Junk Year", "year_group": "abc"}, csrf_page="/admin/lists")
    assert resp.status_code == 303
    with app_db() as db:
        row = db.execute("SELECT * FROM word_lists WHERE name='Junk Year'").fetchone()
    assert row["year_group"] is None


def test_edit_word_list(admin_client):
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('Old')").lastrowid
    post(admin_client, f"/admin/lists/{lid}/edit",
         {"name": "New", "year_group": "5"}, csrf_page=f"/admin/lists/{lid}/edit")
    with app_db() as db:
        row = db.execute("SELECT * FROM word_lists WHERE id=?", (lid,)).fetchone()
    assert (row["name"], row["year_group"]) == ("New", 5)


def test_edit_unknown_list_404s(admin_client):
    resp = admin_client.get("/admin/lists/99999/edit")
    assert resp.status_code == 404


def test_delete_word_list_cascades_words(admin_client):
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('Doomed')").lastrowid
        db.execute("INSERT INTO words (word, list_id) VALUES ('cat', ?)", (lid,))
    post(admin_client, f"/admin/lists/{lid}/delete", {}, csrf_page="/admin/lists")
    with app_db() as db:
        assert db.execute("SELECT * FROM word_lists WHERE id=?", (lid,)).fetchone() is None
        assert db.execute("SELECT COUNT(*) AS c FROM words WHERE list_id=?", (lid,)).fetchone()["c"] == 0


def test_delete_word_list_preserves_legacy_sessions(admin_client):
    """Regression: legacy sessions referencing the list used to make the
    delete fail with a foreign-key error; now they become 'Mixed practice'."""
    child_id = make_child()
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('Doomed')").lastrowid
        sid = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',?,?,16,20)",
            (child_id, lid),
        ).lastrowid
    resp = post(admin_client, f"/admin/lists/{lid}/delete", {}, csrf_page="/admin/lists")
    assert resp.status_code == 303
    with app_db() as db:
        row = db.execute("SELECT * FROM test_sessions WHERE id=?", (sid,)).fetchone()
    assert row is not None
    assert row["list_id"] is None


# ── Words ──────────────────────────────────────────────────────────────────

def test_add_word_is_stripped_and_lowercased(admin_client):
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
    post(admin_client, f"/admin/lists/{lid}/words/add",
         {"word": "  CaT  "}, csrf_page=f"/admin/lists/{lid}/edit")
    with app_db() as db:
        row = db.execute("SELECT word FROM words WHERE list_id=?", (lid,)).fetchone()
    assert row["word"] == "cat"


def test_add_duplicate_word_ignored(admin_client):
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
    for _ in range(2):
        post(admin_client, f"/admin/lists/{lid}/words/add",
             {"word": "cat"}, csrf_page=f"/admin/lists/{lid}/edit")
    with app_db() as db:
        count = db.execute("SELECT COUNT(*) AS c FROM words WHERE list_id=?", (lid,)).fetchone()["c"]
    assert count == 1


def test_delete_word(admin_client):
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
        wid = db.execute("INSERT INTO words (word, list_id) VALUES ('cat', ?)", (lid,)).lastrowid
    post(admin_client, f"/admin/lists/{lid}/words/{wid}/delete", {},
         csrf_page=f"/admin/lists/{lid}/edit")
    with app_db() as db:
        assert db.execute("SELECT * FROM words WHERE id=?", (wid,)).fetchone() is None


def test_delete_word_requires_matching_list(admin_client):
    """word_id under a different list_id in the URL must not delete."""
    with app_db() as db:
        lid1 = db.execute("INSERT INTO word_lists (name) VALUES ('L1')").lastrowid
        lid2 = db.execute("INSERT INTO word_lists (name) VALUES ('L2')").lastrowid
        wid = db.execute("INSERT INTO words (word, list_id) VALUES ('cat', ?)", (lid1,)).lastrowid
    post(admin_client, f"/admin/lists/{lid2}/words/{wid}/delete", {},
         csrf_page=f"/admin/lists/{lid1}/edit")
    with app_db() as db:
        assert db.execute("SELECT * FROM words WHERE id=?", (wid,)).fetchone() is not None


# ── Children ───────────────────────────────────────────────────────────────

def test_create_child_with_unlocks(admin_client):
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
    resp = post(admin_client, "/admin/children/new", {
        "name": "  Bobby  ", "dob": "2016-01-01", "password": "fishfingers",
        "unlock_lists": [lid],
    }, csrf_page="/admin/children/new")
    assert resp.status_code == 303
    with app_db() as db:
        child = db.execute("SELECT * FROM users WHERE name='Bobby'").fetchone()
        unlocks = db.execute(
            "SELECT list_id FROM user_list_unlocks WHERE user_id=?", (child["id"],)
        ).fetchall()
    assert child["is_admin"] == 0
    assert verify_password("fishfingers", child["password_hash"])
    assert [r["list_id"] for r in unlocks] == [lid]


def test_edit_child_without_password_keeps_old_hash(admin_client):
    child_id = make_child()
    post(admin_client, f"/admin/children/{child_id}/edit", {
        "name": "Robert", "dob": "2016-02-02", "new_password": "",
    }, csrf_page=f"/admin/children/{child_id}/edit")
    with app_db() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (child_id,)).fetchone()
    assert row["name"] == "Robert"
    assert row["dob"] == "2016-02-02"
    assert row["password_hash"] == "hash"  # unchanged


def test_edit_child_with_password_changes_hash(admin_client):
    child_id = make_child()
    post(admin_client, f"/admin/children/{child_id}/edit", {
        "name": "Bobby", "dob": "2016-01-01", "new_password": "newpass",
    }, csrf_page=f"/admin/children/{child_id}/edit")
    with app_db() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (child_id,)).fetchone()
    assert verify_password("newpass", row["password_hash"])


def test_edit_child_replaces_unlocks(admin_client):
    child_id = make_child()
    with app_db() as db:
        lid1 = db.execute("INSERT INTO word_lists (name) VALUES ('L1')").lastrowid
        lid2 = db.execute("INSERT INTO word_lists (name) VALUES ('L2')").lastrowid
        db.execute(
            "INSERT INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,'2025-01-01')",
            (child_id, lid1),
        )
    post(admin_client, f"/admin/children/{child_id}/edit", {
        "name": "Bobby", "dob": "2016-01-01", "new_password": "",
        "unlock_lists": [lid2],
    }, csrf_page=f"/admin/children/{child_id}/edit")
    with app_db() as db:
        unlocks = [
            r["list_id"] for r in
            db.execute("SELECT list_id FROM user_list_unlocks WHERE user_id=?", (child_id,)).fetchall()
        ]
    assert unlocks == [lid2]


def test_delete_child(admin_client):
    child_id = make_child()
    post(admin_client, f"/admin/children/{child_id}/delete", {})
    with app_db() as db:
        assert db.execute("SELECT * FROM users WHERE id=?", (child_id,)).fetchone() is None


def test_delete_cannot_remove_admin_user(admin_client):
    with app_db() as db:
        uid = db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES ('Boss','1990-01-01','h','2025-01-01',1)"
        ).lastrowid
    post(admin_client, f"/admin/children/{uid}/delete", {})
    with app_db() as db:
        assert db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() is not None


def test_child_detail_shows_word_stats_and_mixed_sessions(admin_client):
    """Regression: sessions with no list_id (multi-list practice) were
    dropped from the admin child view by an inner join."""
    child_id = make_child()
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
        wid = db.execute("INSERT INTO words (word, list_id) VALUES ('xylophone', ?)", (lid,)).lastrowid
        sid = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',?,NULL,14,20)",
            (child_id,),
        ).lastrowid
        db.execute(
            """INSERT INTO spelling_attempts
               (timestamp, user_id, word_id, correct, attempt_number, session_id)
               VALUES ('2025-01-01',?,?,1,1,?)""",
            (child_id, wid, sid),
        )
    resp = admin_client.get(f"/admin/children/{child_id}")
    assert resp.status_code == 200
    assert "Mixed practice" in resp.text
    assert "xylophone" in resp.text


def test_child_detail_unknown_child_404s(admin_client):
    assert admin_client.get("/admin/children/99999").status_code == 404


def test_unlock_quick_action_is_idempotent(admin_client):
    child_id = make_child()
    with app_db() as db:
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
    for _ in range(2):
        post(admin_client, f"/admin/children/{child_id}/unlock",
             {"list_id": lid}, csrf_page=f"/admin/children/{child_id}")
    with app_db() as db:
        count = db.execute(
            "SELECT COUNT(*) AS c FROM user_list_unlocks WHERE user_id=?", (child_id,)
        ).fetchone()["c"]
    assert count == 1


# ── Audio cache warm ───────────────────────────────────────────────────────

def test_warm_audio_cache_reports_count(admin_client):
    with app_db() as db:
        db.execute("DELETE FROM words")  # replace curriculum with two words
        lid = db.execute("INSERT INTO word_lists (name) VALUES ('L')").lastrowid
        db.execute("INSERT INTO words (word, list_id) VALUES ('cat', ?)", (lid,))
        db.execute("INSERT INTO words (word, list_id) VALUES ('dog', ?)", (lid,))
    resp = post(admin_client, "/admin/warm-audio-cache", {})
    assert resp.headers["location"] == "/admin/?warmed=2"
    with app_db() as db:
        count = db.execute("SELECT COUNT(*) AS c FROM audio_cache").fetchone()["c"]
    assert count == 2


# ── CSRF enforcement on admin posts ────────────────────────────────────────

def test_admin_posts_reject_bad_csrf(admin_client):
    resp = admin_client.post(
        "/admin/lists/create",
        data={"name": "X", "year_group": "", "csrf_token": "forged"},
        follow_redirects=False,
    )
    assert resp.status_code == 403

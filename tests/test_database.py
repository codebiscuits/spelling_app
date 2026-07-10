import sqlite3

import pytest

import database
from database import init_db, get_db
from tests.conftest import make_user, make_list, make_words, make_session, record_attempt


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DB_PATH", path)
    return path


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def table_names(con):
    return {
        r["name"] for r in
        con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def column_names(con, table):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


# ── init_db ────────────────────────────────────────────────────────────────

def test_init_db_creates_all_tables(db_file):
    init_db()
    con = connect(db_file)
    assert {
        "users", "word_lists", "words", "test_sessions", "spelling_attempts",
        "user_list_unlocks", "user_badges", "test_badges", "audio_cache",
    } <= table_names(con)
    con.close()


def test_init_db_is_idempotent(db_file):
    init_db()
    con = connect(db_file)
    con.execute(
        "INSERT INTO users (name, dob, password_hash, date_created) VALUES ('A','2015-01-01','h','2025-01-01')"
    )
    con.commit()
    con.close()

    init_db()  # second run must not error or destroy data

    con = connect(db_file)
    assert con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 1
    con.close()


def test_get_db_commits_on_success(db_file):
    init_db()
    with get_db() as db:
        db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created) VALUES ('A','2015-01-01','h','2025-01-01')"
        )
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 1


def test_get_db_rolls_back_on_exception(db_file):
    init_db()
    with pytest.raises(RuntimeError):
        with get_db() as db:
            db.execute(
                "INSERT INTO users (name, dob, password_hash, date_created) VALUES ('A','2015-01-01','h','2025-01-01')"
            )
            raise RuntimeError("boom")
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0


# ── Migrations ─────────────────────────────────────────────────────────────

OLD_SCHEMA = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    dob           TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    date_created  TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    mode          TEXT NOT NULL DEFAULT 'audio'
);

CREATE TABLE word_lists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    year_group INTEGER
);

CREATE TABLE words (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    word    TEXT NOT NULL,
    list_id INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    UNIQUE(word, list_id)
);

CREATE TABLE test_sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id   INTEGER NOT NULL REFERENCES word_lists(id),
    score     INTEGER NOT NULL,
    max_score INTEGER NOT NULL
);
"""


@pytest.fixture
def old_db_file(db_file):
    """A database built with the pre-migration schema, containing data."""
    con = connect(db_file)
    con.executescript(OLD_SCHEMA)
    con.execute("INSERT INTO word_lists (name, year_group) VALUES ('Old List', 1)")
    con.execute("INSERT INTO words (word, list_id) VALUES ('cat', 1)")
    con.execute(
        "INSERT INTO users (name, dob, password_hash, date_created) VALUES ('A','2015-01-01','h','2025-01-01')"
    )
    con.execute(
        "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-01',1,1,16,20)"
    )
    con.commit()
    con.close()
    return db_file


def test_migration_adds_context_sentence_column(old_db_file):
    init_db()
    con = connect(old_db_file)
    assert "context_sentence" in column_names(con, "words")
    # Existing rows survive with NULL sentence
    row = con.execute("SELECT * FROM words").fetchone()
    assert row["word"] == "cat"
    assert row["context_sentence"] is None
    con.close()


def test_migration_makes_session_list_id_nullable(old_db_file):
    init_db()
    con = connect(old_db_file)
    # Old data preserved
    row = con.execute("SELECT * FROM test_sessions").fetchone()
    assert (row["id"], row["list_id"], row["score"]) == (1, 1, 16)
    # NULL list_id now accepted
    con.execute(
        "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES ('2025-01-02',1,NULL,0,20)"
    )
    con.commit()
    con.close()


def test_migrations_are_idempotent(old_db_file):
    init_db()
    init_db()
    con = connect(old_db_file)
    assert con.execute("SELECT COUNT(*) AS c FROM test_sessions").fetchone()["c"] == 1
    con.close()


# ── Foreign-key cascades ───────────────────────────────────────────────────

def test_deleting_user_cascades_activity(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid)
    db.execute(
        "INSERT INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,'2025-01-01')",
        (uid, lid),
    )
    db.execute(
        "INSERT INTO user_badges (user_id, list_id, badge_type, earned_at) VALUES (?,?,'medal','2025-01-01')",
        (uid, lid),
    )
    db.execute(
        "INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,'2025-01-01')",
        (uid, sid),
    )
    db.commit()

    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()

    for table in ("test_sessions", "spelling_attempts", "user_list_unlocks", "user_badges", "test_badges"):
        assert db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"] == 0


def test_deleting_list_cascades_words_and_attempts(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog"])
    sid = make_session(db, uid, None)
    record_attempt(db, uid, wids[0], sid)

    db.execute("DELETE FROM word_lists WHERE id=?", (lid,))
    db.commit()

    assert db.execute("SELECT COUNT(*) AS c FROM words").fetchone()["c"] == 0
    assert db.execute("SELECT COUNT(*) AS c FROM spelling_attempts").fetchone()["c"] == 0
    # The session itself survives (list_id is NULL for multi-list sessions)
    assert db.execute("SELECT COUNT(*) AS c FROM test_sessions").fetchone()["c"] == 1

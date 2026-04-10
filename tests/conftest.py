import sqlite3
import pytest
from database import SCHEMA


@pytest.fixture
def db():
    """In-memory SQLite database with the full app schema applied."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    con.commit()
    yield con
    con.close()


# ── Helpers ────────────────────────────────────────────────────────────────

def make_user(db, name="Alice"):
    cur = db.execute(
        "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
        (name, "2015-01-01", "hash", "2025-01-01T00:00:00+00:00"),
    )
    db.commit()
    return cur.lastrowid


def make_list(db, name="Test List", year_group=None):
    cur = db.execute(
        "INSERT INTO word_lists (name, year_group) VALUES (?,?)", (name, year_group)
    )
    db.commit()
    return cur.lastrowid


def make_words(db, list_id, words):
    """Insert words and return list of their IDs."""
    ids = []
    for w in words:
        cur = db.execute(
            "INSERT INTO words (word, list_id) VALUES (?,?)", (w, list_id)
        )
        ids.append(cur.lastrowid)
    db.commit()
    return ids


def make_session(db, user_id, list_id, score=0):
    cur = db.execute(
        "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES (?,?,?,?,20)",
        ("2025-01-01T00:00:00+00:00", user_id, list_id, score),
    )
    db.commit()
    return cur.lastrowid


def record_attempt(db, user_id, word_id, session_id, attempt_number=1, correct=1):
    db.execute(
        """INSERT INTO spelling_attempts
           (timestamp, user_id, word_id, correct, attempt_number, session_id)
           VALUES (?,?,?,?,?,?)""",
        ("2025-01-01T00:00:00+00:00", user_id, word_id, correct, attempt_number, session_id),
    )
    db.commit()

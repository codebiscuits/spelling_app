import os
import re
import sqlite3

import bcrypt
import pytest

# Must be set before `main` is first imported: SECRET_KEY is required at
# import time, and HTTPS_ONLY must be off or the TestClient (plain http)
# drops the session cookie.  load_dotenv() in main does not override
# values already present in the environment.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ["HTTPS_ONLY"] = "false"

TEST_PASSWORD = "correct horse"
# rounds=4 keeps bcrypt fast in tests; production uses the default cost
TEST_PASSWORD_HASH = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()

os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD_HASH"] = TEST_PASSWORD_HASH

from database import SCHEMA  # noqa: E402


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


# ── App / route-test fixtures ──────────────────────────────────────────────

class FakeTTS:
    """Stands in for gTTS: writes a plausible-sized fake mp3, no network."""

    def __init__(self, text, lang="en", tld="co.uk"):
        self.text = text

    def save(self, path):
        with open(path, "wb") as f:
            f.write(b"x" * 3000)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on a fresh temp database with gTTS faked out.

    The app lifespan runs init_db() and seeds the curriculum into the
    temp database on entry.
    """
    import database
    import services.tts as tts_module

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(tts_module, "AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setattr(tts_module, "gTTS", FakeTTS)

    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        yield c


def app_db():
    """Connection to the temp database the client fixture is running on."""
    import database
    return database.get_db()


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "No CSRF token found in page"
    return match.group(1)


def get_csrf(client, url="/login") -> str:
    resp = client.get(url)
    assert resp.status_code == 200
    return extract_csrf(resp.text)


def login(client, username, password):
    csrf = get_csrf(client, "/login")
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


@pytest.fixture
def admin_client(client):
    resp = login(client, "admin", TEST_PASSWORD)
    assert resp.headers["location"] == "/admin/"
    return client


@pytest.fixture
def child_client(client):
    """Client logged in as a child named Alice; child id on .child_id."""
    with app_db() as db:
        cur = db.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            ("Alice", "2017-06-01", TEST_PASSWORD_HASH, "2025-01-01T00:00:00+00:00"),
        )
        child_id = cur.lastrowid
    resp = login(client, "Alice", TEST_PASSWORD)
    assert resp.headers["location"] == "/child/dashboard"
    client.child_id = child_id
    return client


def setup_practice_list(child_id, words, year_group=None, sentences=None, name="Practice"):
    """Create a word list, add words, unlock it for the child.

    Returns (list_id, {word: word_id}).
    """
    sentences = sentences or {}
    with app_db() as db:
        cur = db.execute(
            "INSERT INTO word_lists (name, year_group) VALUES (?,?)", (name, year_group)
        )
        list_id = cur.lastrowid
        word_ids = {}
        for w in words:
            cur = db.execute(
                "INSERT INTO words (word, list_id, context_sentence) VALUES (?,?,?)",
                (w, list_id, sentences.get(w)),
            )
            word_ids[w] = cur.lastrowid
        db.execute(
            "INSERT INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,?)",
            (child_id, list_id, "2025-01-01T00:00:00+00:00"),
        )
    return list_id, word_ids


def current_word(client):
    """GET /test/word and return (word_id, word_text, response)."""
    resp = client.get("/test/word")
    assert resp.status_code == 200
    match = re.search(r'name="word_id" value="(\d+)"', resp.text)
    assert match, "No word_id field on test page"
    word_id = int(match.group(1))
    with app_db() as db:
        row = db.execute("SELECT word FROM words WHERE id=?", (word_id,)).fetchone()
    return word_id, row["word"], resp


def submit_answer(client, word_id, answer):
    return client.post(
        "/test/word",
        data={"word_id": word_id, "answer": answer},
        follow_redirects=False,
    )


def run_full_test(client, answer_fn):
    """Drive a whole test, declining the top-up offer; answer_fn(word)
    returns the answer to give."""
    client.get("/test/start")
    for _ in range(50):
        resp = client.get("/test/word", follow_redirects=False)
        if resp.status_code == 303:
            assert resp.headers["location"] == "/test/topup"
            # Skip the top-up offer ("No thanks" is a plain results link)
            return client.get("/test/results")
        word_id, word, _ = current_word(client)
        submit_answer(client, word_id, answer_fn(word))
    raise AssertionError("Test never finished")

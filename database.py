import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "spelling.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    dob           TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    date_created  TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    mode          TEXT NOT NULL DEFAULT 'audio'
);

CREATE TABLE IF NOT EXISTS word_lists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    year_group INTEGER
);

CREATE TABLE IF NOT EXISTS words (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    word             TEXT NOT NULL,
    list_id          INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    context_sentence TEXT,
    UNIQUE(word, list_id)
);

CREATE TABLE IF NOT EXISTS test_sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id   INTEGER NOT NULL REFERENCES word_lists(id),
    score     INTEGER NOT NULL,
    max_score INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS spelling_attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id        INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    correct        INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    session_id     INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_list_unlocks (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id     INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    unlocked_at TEXT NOT NULL,
    PRIMARY KEY (user_id, list_id)
);

CREATE TABLE IF NOT EXISTS user_badges (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id    INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    badge_type TEXT NOT NULL,
    earned_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, list_id, badge_type)
);

CREATE TABLE IF NOT EXISTS test_badges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    earned_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audio_cache (
    word_text  TEXT PRIMARY KEY,
    file_path  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        # Migration: add context_sentence to existing databases
        try:
            con.execute("ALTER TABLE words ADD COLUMN context_sentence TEXT")
            con.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: make test_sessions.list_id nullable for multi-list sessions
        try:
            cols = {r["name"]: r for r in con.execute("PRAGMA table_info(test_sessions)").fetchall()}
            if cols.get("list_id") and cols["list_id"]["notnull"]:
                con.executescript("""
                    PRAGMA foreign_keys=OFF;
                    CREATE TABLE test_sessions_new (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        list_id   INTEGER REFERENCES word_lists(id),
                        score     INTEGER NOT NULL,
                        max_score INTEGER NOT NULL
                    );
                    INSERT INTO test_sessions_new SELECT * FROM test_sessions;
                    DROP TABLE test_sessions;
                    ALTER TABLE test_sessions_new RENAME TO test_sessions;
                    PRAGMA foreign_keys=ON;
                """)
                con.commit()
        except Exception:
            pass
    finally:
        con.close()

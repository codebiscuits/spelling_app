import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

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
    year_group INTEGER,
    position   INTEGER NOT NULL DEFAULT 0   -- curriculum order of lists (1 = first)
);

CREATE TABLE IF NOT EXISTS words (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    word             TEXT NOT NULL,
    list_id          INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    context_sentence TEXT,
    position         INTEGER NOT NULL DEFAULT 0,   -- curriculum order within its list (1 = first)
    UNIQUE(word, list_id)
);

CREATE TABLE IF NOT EXISTS test_sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id   INTEGER REFERENCES word_lists(id),
    score     INTEGER NOT NULL,
    max_score INTEGER NOT NULL,
    subject   TEXT NOT NULL DEFAULT 'spelling'   -- 'spelling' | 'arithmetic'
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

CREATE TABLE IF NOT EXISTS user_game_unlocks (
    user_id   INTEGER NOT NULL REFERENCES users(id),
    game_file TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    source    TEXT NOT NULL,   -- 'badge' | 'admin' | 'launch' (older rows may say 'medal' or 'trophy')
    PRIMARY KEY (user_id, game_file)
);

-- Spelling progression (release 2). All additive: nothing above is changed.
CREATE TABLE IF NOT EXISTS schema_migrations (
    name       TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- The word a child is currently being introduced to. At most one open row
-- (completed_at IS NULL) per child. after_attempt_id is the newest attempt
-- id when the focus began: only ordinary first attempts after it count
-- towards the three-in-a-row that completes the focus.
CREATE TABLE IF NOT EXISTS spelling_focus (
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id          INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    after_attempt_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_spelling_focus_one_open
    ON spelling_focus(user_id) WHERE completed_at IS NULL;

-- The first time a child mastered an item. Never deleted, so re-mastering
-- a forgotten word does not count again. subject lets arithmetic reuse it.
CREATE TABLE IF NOT EXISTS first_mastered (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    item_key    TEXT NOT NULL,
    mastered_at TEXT NOT NULL,
    PRIMARY KEY (user_id, subject, item_key)
);

-- One medal per ten distinct items first mastered. silent=1: backfilled at
-- migration, so no banner and no game unlock.
CREATE TABLE IF NOT EXISTS milestone_medals (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject   TEXT NOT NULL,
    threshold INTEGER NOT NULL,
    earned_at TEXT NOT NULL,
    silent    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, subject, threshold)
);

-- One trophy per list (group_id = word_lists.id for spelling), awarded at
-- the child's first ordinary first attempt at a word from that list.
CREATE TABLE IF NOT EXISTS start_trophies (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject   TEXT NOT NULL,
    group_id  INTEGER NOT NULL,
    earned_at TEXT NOT NULL,
    silent    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, subject, group_id)
);

-- Mastery trophies: the child-facing trophy. One per word list (group_key =
-- word_lists.id as text) and one per times table 2 to 12 (group_key = the
-- table number as text), won when every item in the group has a
-- first_mastered row. Permanent. silent=1 is reserved for quiet awards.
CREATE TABLE IF NOT EXISTS mastery_trophies (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject   TEXT NOT NULL,
    group_key TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    silent    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, subject, group_key)
);

-- Arithmetic practice (release 3). All additive.
-- One row per answer. fact_key names one exact question ('m:3x4' is 3 x 4,
-- 'd:12/3' is 12 / 3). attempt_number: 1 ordinary first, 2 ordinary second
-- (after the clue), 3 top-up. Only attempt_number=1 is learning evidence.
-- session_id points at test_sessions (subject='arithmetic'), so the shared
-- badge and game rules work across both subjects.
CREATE TABLE IF NOT EXISTS arithmetic_attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fact_key       TEXT NOT NULL,
    correct        INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    session_id     INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    response_ms    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_arithmetic_attempts_user_fact
    ON arithmetic_attempts(user_id, fact_key, id);

-- Table-ladder rungs a child has unlocked. Rungs never lock again.
CREATE TABLE IF NOT EXISTS arithmetic_rungs (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rung        INTEGER NOT NULL,
    unlocked_at TEXT NOT NULL,
    PRIMARY KEY (user_id, rung)
);

-- The fact family a child is being introduced to. At most one open row
-- (completed_at IS NULL) per child. after_attempt_id works as in
-- spelling_focus. A family row, once written, also marks it introduced.
CREATE TABLE IF NOT EXISTS arithmetic_focus (
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_key       TEXT NOT NULL,
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    after_attempt_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, family_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_arithmetic_focus_one_open
    ON arithmetic_focus(user_id) WHERE completed_at IS NULL;

CREATE TABLE IF NOT EXISTS user_game_plays (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_file TEXT NOT NULL,
    played_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_game_plays_recent
    ON user_game_plays (user_id, played_at);

CREATE TABLE IF NOT EXISTS user_game_launches (
    nonce      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_file  TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_game_launches_expires
    ON user_game_launches (expires_at);

CREATE TABLE IF NOT EXISTS user_game_credits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL UNIQUE REFERENCES test_sessions(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score      INTEGER NOT NULL,
    status     TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available', 'consumed', 'forfeited')),
    earned_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_game_credits_user
    ON user_game_credits (user_id, id);
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


def _add_column(con, table: str, column_def: str) -> None:
    try:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        con.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists


def _migrate_progression(con) -> None:
    """Release 2 migration. Additive only: new columns and new tables, and
    data written into those. No existing row or column is changed, so
    reverting the code needs no database restore. Safe to run repeatedly."""
    _add_column(con, "word_lists", "position INTEGER NOT NULL DEFAULT 0")
    _add_column(con, "words", "position INTEGER NOT NULL DEFAULT 0")
    _backfill_positions(con)
    con.commit()

    already = con.execute(
        "SELECT 1 FROM schema_migrations WHERE name=?", (PROGRESSION_MIGRATION,)
    ).fetchone()
    if not already:
        from services.progression_backfill import backfill_awards
        now = datetime.now(timezone.utc).isoformat()
        backfill_awards(con, now)
        con.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?,?)",
            (PROGRESSION_MIGRATION, now),
        )
        con.commit()


PROGRESSION_MIGRATION = "spelling_progression_v1"


def _migrate_arithmetic(con) -> None:
    """Release 3 migration. Additive only: one new column on test_sessions
    (every existing row becomes 'spelling' through the default) and the new
    arithmetic tables, which the schema script creates. Safe to repeat."""
    _add_column(con, "test_sessions", "subject TEXT NOT NULL DEFAULT 'spelling'")


def _backfill_positions(con) -> None:
    """Give every list and word still at position 0 a curriculum position.
    Lists: year group, then id. Words: their order in the seed file where
    the word is in the seed, then id. Rows that already have a position
    (set by the seed or the admin pages) are left alone."""
    from seed.curriculum_words import CURRICULUM

    next_list = con.execute("SELECT COALESCE(MAX(position),0) FROM word_lists").fetchone()[0]
    unpositioned = con.execute(
        """SELECT id FROM word_lists WHERE position=0
           ORDER BY year_group IS NULL, year_group, id"""
    ).fetchall()
    for row in unpositioned:
        next_list += 1
        con.execute("UPDATE word_lists SET position=? WHERE id=?", (next_list, row["id"]))

    for lst in con.execute("SELECT id, name, year_group FROM word_lists").fetchall():
        seed_words = CURRICULUM.get(lst["year_group"])
        if seed_words is None or lst["name"] != f"Year {lst['year_group']}\u2013{lst['year_group'] + 1}":
            seed_words = []
        seed_order: dict[str, int] = {}
        for w in seed_words:
            seed_order.setdefault(w.lower(), len(seed_order))
        todo = con.execute(
            "SELECT id, word FROM words WHERE list_id=? AND position=0", (lst["id"],)
        ).fetchall()
        if not todo:
            continue
        todo.sort(key=lambda r: (r["word"] not in seed_order, seed_order.get(r["word"], 0), r["id"]))
        n = con.execute(
            "SELECT COALESCE(MAX(position),0) FROM words WHERE list_id=?", (lst["id"],)
        ).fetchone()[0]
        for r in todo:
            n += 1
            con.execute("UPDATE words SET position=? WHERE id=?", (n, r["id"]))


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

        _migrate_progression(con)

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

        # After the legacy rebuild above, whose copy relies on the old
        # column list of test_sessions.
        _migrate_arithmetic(con)
        # Migration: retain terminal credit status so replayed result cookies
        # cannot re-mint a credit after it was spent or forfeited.
        try:
            con.execute(
                "ALTER TABLE user_game_credits ADD COLUMN status TEXT NOT NULL DEFAULT 'available'"
            )
            con.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists, or this database predates game credits

        # Launch gift (§1.3): every child with zero user_game_unlocks rows
        # is gifted the first reward-tier game. Idempotent; re-triggers if
        # an admin re-locks a child back to zero rows.
        from templates_env import REWARD_GAMES

        if REWARD_GAMES:
            first_game_file = REWARD_GAMES[0]["file"]
            now = datetime.now(timezone.utc).isoformat()
            childless_ids = con.execute(
                """SELECT id FROM users
                   WHERE is_admin=0
                     AND id NOT IN (SELECT DISTINCT user_id FROM user_game_unlocks)"""
            ).fetchall()
            for row in childless_ids:
                con.execute(
                    """INSERT OR IGNORE INTO user_game_unlocks
                       (user_id, game_file, earned_at, source) VALUES (?,?,?,?)""",
                    (row["id"], first_game_file, now, "launch"),
                )
            con.commit()
    finally:
        con.close()

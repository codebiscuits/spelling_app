"""Release 3 migration: additive, idempotent, old data untouched."""
import hashlib
import sqlite3

import pytest

import database
from tests.old_schema import OLD_SCHEMA
from tests.test_progression_migration import OLD_TABLES

ARITHMETIC_TABLES = ["arithmetic_attempts", "arithmetic_rungs", "arithmetic_focus"]
RELEASE2_TABLES = ["spelling_focus", "first_mastered", "milestone_medals", "start_trophies",
                   "schema_migrations"]
TS = "2026-05-01T10:00:00+00:00"


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def fingerprint(con, tables):
    out = {}
    for table, cols in tables.items():
        rows = con.execute(f"SELECT {cols} FROM {table} ORDER BY rowid").fetchall()
        out[table] = (len(rows), hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest())
    return out


def populate(con):
    con.execute("INSERT INTO word_lists (id,name,year_group) VALUES (1,'Year 1–2',1)")
    con.execute("INSERT INTO words (id,word,list_id) VALUES (1,'the',1)")
    con.execute("INSERT INTO users (id,name,dob,password_hash,date_created,is_admin) VALUES (1,'Ollie','2016-01-01','h',?,0)", (TS,))
    con.execute("INSERT INTO test_sessions (id,timestamp,user_id,list_id,score,max_score) VALUES (1,?,1,1,17,20)", (TS,))
    for _ in range(3):
        con.execute("INSERT INTO spelling_attempts (timestamp,user_id,word_id,correct,attempt_number,session_id) VALUES (?,1,1,1,1,1)", (TS,))
    # already gifted, so the old launch-gift step has nothing to add
    con.execute("INSERT INTO user_game_unlocks VALUES (1,'gear_garden_v1.html',?,'launch')", (TS,))
    con.execute("INSERT INTO test_badges (user_id,session_id,earned_at) VALUES (1,1,?)", (TS,))
    con.commit()


@pytest.fixture
def old_db(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")
    monkeypatch.setattr(database, "DB_PATH", path)
    con = connect(path)
    con.executescript(OLD_SCHEMA)
    populate(con)
    con.close()
    return path


def table_names(con):
    return {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_migration_adds_tables_and_one_defaulted_column(old_db):
    database.init_db()
    con = connect(old_db)
    assert set(ARITHMETIC_TABLES) <= table_names(con)
    cols = {r["name"]: r for r in con.execute("PRAGMA table_info(test_sessions)")}
    assert set(cols) == {"id", "timestamp", "user_id", "list_id", "score", "max_score", "subject"}
    assert cols["subject"]["dflt_value"] == "'spelling'" and cols["subject"]["notnull"] == 1
    assert con.execute("SELECT subject FROM test_sessions").fetchall()[0]["subject"] == "spelling"
    for t in ARITHMETIC_TABLES:
        assert con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0


def test_old_data_is_untouched(old_db):
    con = connect(old_db)
    before = fingerprint(con, OLD_TABLES)
    con.close()
    database.init_db()
    con = connect(old_db)
    assert fingerprint(con, OLD_TABLES) == before


def test_migration_is_idempotent(old_db):
    database.init_db()
    con = connect(old_db)
    con.execute("INSERT INTO arithmetic_rungs VALUES (1,1,?)", (TS,))
    con.execute("INSERT INTO test_sessions (timestamp,user_id,list_id,score,max_score,subject) "
                "VALUES (?,1,NULL,5,20,'arithmetic')", (TS,))
    con.commit()
    snap = {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
            for t in ARITHMETIC_TABLES + RELEASE2_TABLES + ["test_sessions"]}
    con.close()
    database.init_db()
    database.init_db()
    con = connect(old_db)
    assert snap == {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                    for t in snap}


def test_release_two_database_upgrades_without_losing_rows(old_db):
    """A database already migrated for release 2 (no subject column, no
    arithmetic tables), with live data, upgrades in place."""
    database.init_db()
    con = connect(old_db)
    con.execute("DROP INDEX IF EXISTS idx_arithmetic_attempts_user_fact")
    con.execute("DROP INDEX IF EXISTS idx_arithmetic_focus_one_open")
    for t in ARITHMETIC_TABLES:
        con.execute(f"DROP TABLE {t}")
    con.execute("ALTER TABLE test_sessions DROP COLUMN subject")
    con.commit()
    before = {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
              for t in ["users", "words", "word_lists", "spelling_attempts", "test_badges",
                        "first_mastered", "milestone_medals", "start_trophies", "spelling_focus",
                        "user_game_unlocks", "user_list_unlocks"]}
    sessions = [tuple(r) for r in con.execute("SELECT * FROM test_sessions")]
    con.close()

    database.init_db()
    con = connect(old_db)
    assert set(ARITHMETIC_TABLES) <= table_names(con)
    assert before == {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
                      for t in before}
    assert [tuple(r)[:-1] for r in con.execute("SELECT * FROM test_sessions")] == sessions
    assert con.execute("SELECT subject FROM test_sessions").fetchone()[0] == "spelling"


def test_legacy_not_null_list_id_database_keeps_its_sessions(tmp_path, monkeypatch):
    """The older rebuild of test_sessions copies columns by position; it must
    still work now that a subject column exists."""
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(database, "DB_PATH", path)
    con = connect(path)
    con.executescript(OLD_SCHEMA.replace(
        "list_id   INTEGER REFERENCES word_lists(id),", "list_id   INTEGER NOT NULL REFERENCES word_lists(id),"))
    populate(con)
    con.close()
    database.init_db()
    con = connect(path)
    row = con.execute("SELECT * FROM test_sessions").fetchone()
    assert (row["id"], row["user_id"], row["list_id"], row["score"], row["subject"]) == (1, 1, 1, 17, "spelling")


def test_spelling_behaviour_is_unchanged_after_migration(old_db):
    database.init_db()
    from services import spelling_progression as sp
    con = connect(old_db)
    plan = sp.plan_practice(1, con)
    assert plan.kind in ("normal", "baseline")
    con.close()

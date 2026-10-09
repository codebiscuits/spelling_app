"""Release 2 migration, run against a database built with the OLD schema."""
import hashlib
import sqlite3

import pytest

import database
from seed.curriculum_words import CURRICULUM
from tests.old_schema import OLD_SCHEMA

OLD_TABLES = {
    "users": "id,name,dob,password_hash,date_created,is_admin,mode",
    "word_lists": "id,name,year_group",
    "words": "id,word,list_id,context_sentence",
    "test_sessions": "id,timestamp,user_id,list_id,score,max_score",
    "spelling_attempts": "id,timestamp,user_id,word_id,correct,attempt_number,session_id",
    "user_list_unlocks": "user_id,list_id,unlocked_at",
    "user_badges": "user_id,list_id,badge_type,earned_at",
    "test_badges": "id,user_id,session_id,earned_at",
    "audio_cache": "word_text,file_path,created_at",
    "user_game_unlocks": "user_id,game_file,earned_at,source",
}
NEW_TABLES = ["spelling_focus", "first_mastered", "milestone_medals", "start_trophies"]
Y12 = CURRICULUM[1]


def fingerprint(con):
    """Row count and checksum of every old table, using only old columns."""
    out = {}
    for table, cols in OLD_TABLES.items():
        rows = con.execute(f"SELECT {cols} FROM {table} ORDER BY rowid").fetchall()
        out[table] = (len(rows), hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest())
    return out


@pytest.fixture
def old_db(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")
    monkeypatch.setattr(database, "DB_PATH", path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(OLD_SCHEMA)
    ts = "2026-05-01T10:00:00+00:00"

    # Lists inserted in an order that disagrees with year_group: an admin list
    # (no year group) first, then Year 3-4, then Year 1-2.
    con.execute("INSERT INTO word_lists (id, name, year_group) VALUES (1,'Admin extras',NULL)")
    con.execute("INSERT INTO word_lists (id, name, year_group) VALUES (2,'Year 3–4',3)")
    con.execute("INSERT INTO word_lists (id, name, year_group) VALUES (3,'Year 1–2',1)")
    # Year 1-2 words inserted in a scrambled order, plus one that is not in the seed
    scrambled = ["water", "the", "zzz-custom", "said", "a", "because", "people", "do", "to", "today",
                 "of", "are", "has", "his"]
    for i, w in enumerate(scrambled, start=1):
        con.execute("INSERT INTO words (id, word, list_id) VALUES (?,?,3)", (100 + i, w))
    con.execute("INSERT INTO words (id, word, list_id) VALUES (200,'banana',1)")
    con.execute("INSERT INTO words (id, word, list_id) VALUES (201,'apple',1)")
    con.execute("INSERT INTO words (id, word, list_id) VALUES (300,'caught',2)")

    for uid, name in ((1, "Ollie"), (2, "Emma"), (3, "Newbie")):
        con.execute(
            "INSERT INTO users (id,name,dob,password_hash,date_created,is_admin) VALUES (?,?,?,?,?,0)",
            (uid, name, "2016-01-01", "h", ts),
        )
        con.execute("INSERT INTO user_game_unlocks VALUES (?,?,?,?)", (uid, "gear_garden_v1.html", ts, "launch"))
    con.execute("INSERT INTO user_list_unlocks VALUES (1,3,?)", (ts,))
    con.execute("INSERT INTO user_list_unlocks VALUES (1,2,?)", (ts,))
    con.execute("INSERT INTO user_list_unlocks VALUES (2,3,?)", (ts,))
    con.execute("INSERT INTO user_list_unlocks VALUES (3,3,?)", (ts,))

    n = 0

    def session(uid):
        return con.execute(
            "INSERT INTO test_sessions (timestamp,user_id,list_id,score,max_score) VALUES (?,?,NULL,16,20)",
            (ts, uid),
        ).lastrowid

    def attempt(uid, wid, sid, num, ok):
        nonlocal n
        n += 1
        con.execute(
            "INSERT INTO spelling_attempts (timestamp,user_id,word_id,correct,attempt_number,session_id) VALUES (?,?,?,?,?,?)",
            (f"2026-05-{1 + n % 28:02d}T10:00:00+00:00", uid, wid, ok, num, sid),
        )

    # Ollie: 11 words mastered (3 correct each) in list 3, 1 word mastered then
    # slipped, 1 word seen once, 1 word from list 2 wrong, and top-ups on a
    # word he never attempted otherwise.
    s = session(1)
    for wid in range(101, 112):
        for _ in range(3):
            attempt(1, wid, s, 1, 1)
    for ok in (1, 1, 1, 0):
        attempt(1, 112, s, 1, ok)           # mastered then slipped
    attempt(1, 300, s, 1, 0)                 # wrong first try in list 2
    attempt(1, 300, s, 2, 1)
    attempt(1, 200, s, 3, 1)                 # top-up only: list 1 not "started"
    # Emma: 4 words, none mastered
    s2 = session(2)
    for wid in (101, 102, 103, 104):
        attempt(2, wid, s2, 1, 0)
    con.execute("INSERT INTO user_badges VALUES (1,3,'medal',?)", (ts,))
    con.execute("INSERT INTO user_badges VALUES (1,3,'trophy',?)", (ts,))
    con.execute("INSERT INTO test_badges (user_id,session_id,earned_at) VALUES (1,?,?)", (s, ts))
    con.execute("INSERT INTO audio_cache VALUES ('the','static/audio/x.mp3',?)", (ts,))
    con.commit()
    con.close()
    return path


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def count(con, table, where="1=1"):
    return con.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]


def test_migration_is_additive_old_tables_unchanged(old_db):
    con = connect(old_db)
    before = fingerprint(con)
    con.close()
    database.init_db()
    con = connect(old_db)
    assert fingerprint(con) == before
    # Old tables still have exactly their old columns, plus the two new position columns
    cols = {r["name"] for r in con.execute("PRAGMA table_info(words)")}
    assert cols == {"id", "word", "list_id", "context_sentence", "position"}
    cols = {r["name"] for r in con.execute("PRAGMA table_info(word_lists)")}
    assert cols == {"id", "name", "year_group", "position"}
    for table in OLD_TABLES:
        old_cols = [c.strip() for c in OLD_TABLES[table].split(",")]
        now = [r["name"] for r in con.execute(f"PRAGMA table_info({table})")]
        assert all(c in now for c in old_cols)


def test_migration_is_idempotent(old_db):
    database.init_db()
    con = connect(old_db)
    snapshot = {
        t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
        for t in NEW_TABLES + ["schema_migrations"]
    }
    positions = [tuple(r) for r in con.execute(
        "SELECT id, position FROM words UNION ALL SELECT -id, position FROM word_lists ORDER BY 1")]
    old = fingerprint(con)
    con.close()

    database.init_db()
    database.init_db()
    con = connect(old_db)
    assert {
        t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
        for t in NEW_TABLES + ["schema_migrations"]
    } == snapshot
    assert positions == [tuple(r) for r in con.execute(
        "SELECT id, position FROM words UNION ALL SELECT -id, position FROM word_lists ORDER BY 1")]
    assert fingerprint(con) == old


def test_list_positions_follow_year_group_then_id_with_unyeared_lists_last(old_db):
    database.init_db()
    con = connect(old_db)
    rows = con.execute("SELECT id, position FROM word_lists ORDER BY position").fetchall()
    assert [r["id"] for r in rows] == [3, 2, 1]  # Year 1-2, Year 3-4, admin list
    assert [r["position"] for r in rows] == [1, 2, 3]


def test_word_positions_follow_seed_order_then_id_for_non_seed_words(old_db):
    database.init_db()
    con = connect(old_db)
    rows = con.execute("SELECT word FROM words WHERE list_id=3 ORDER BY position").fetchall()
    ordered = [r["word"] for r in rows]
    seed_order = []
    for w in Y12:
        if w.lower() not in seed_order:
            seed_order.append(w.lower())
    expected = sorted(
        [w for w in ordered if w in seed_order], key=seed_order.index
    ) + ["zzz-custom"]
    assert ordered == expected
    assert ordered[:3] == ["the", "a", "do"]          # seed order, not insertion or alphabet
    assert ordered[-1] == "zzz-custom"                # not in the seed: after seeded words
    # Non-seed list: ordered by id
    admin = con.execute("SELECT word FROM words WHERE list_id=1 ORDER BY position").fetchall()
    assert [r["word"] for r in admin] == ["banana", "apple"]
    positions = [r["position"] for r in con.execute("SELECT position FROM words WHERE list_id=3 ORDER BY position")]
    assert positions == list(range(1, 15))


def test_existing_mastery_is_recorded_and_medals_are_silent(old_db):
    database.init_db()
    con = connect(old_db)
    # Ollie: words 101-111 mastered; 112 mastered-then-slipped does not count -> 11 words
    mastered = {r["item_key"] for r in con.execute(
        "SELECT item_key FROM first_mastered WHERE user_id=1 AND subject='spelling'")}
    assert mastered == {str(w) for w in range(101, 112)}
    medals = con.execute("SELECT threshold, silent FROM milestone_medals WHERE user_id=1").fetchall()
    assert [(m["threshold"], m["silent"]) for m in medals] == [(10, 1)]
    assert count(con, "milestone_medals", "user_id IN (2,3)") == 0
    assert count(con, "first_mastered", "user_id IN (2,3)") == 0


def test_start_trophies_are_silent_for_every_list_with_ordinary_attempts(old_db):
    database.init_db()
    con = connect(old_db)
    rows = con.execute("SELECT user_id, group_id, silent FROM start_trophies ORDER BY user_id, group_id").fetchall()
    # Ollie: lists 3 and 2 (list 1 had only a top-up). Emma: list 3. Newbie: none.
    assert [(r["user_id"], r["group_id"], r["silent"]) for r in rows] == [(1, 2, 1), (1, 3, 1), (2, 3, 1)]


def test_migration_creates_no_focus_rows_and_no_game_unlocks(old_db):
    con = connect(old_db)
    games_before = [tuple(r) for r in con.execute("SELECT * FROM user_game_unlocks ORDER BY 1,2")]
    con.close()
    database.init_db()
    con = connect(old_db)
    assert count(con, "spelling_focus") == 0
    assert [tuple(r) for r in con.execute("SELECT * FROM user_game_unlocks ORDER BY 1,2")] == games_before


def test_existing_child_keeps_lists_and_next_practice_introduces_next_locked_word(old_db):
    database.init_db()
    from services import spelling_progression as sp
    con = connect(old_db)
    lists_before = sp.available_list_ids(1, con)
    assert lists_before == [3, 2]
    plan = sp.plan_practice(1, con)
    assert plan.kind == "normal"
    focus = con.execute("SELECT word FROM words WHERE id=?", (plan.focus_id,)).fetchone()["word"]
    # Earliest-position unseen word in the earliest list: the seed order's
    # first word the child has not attempted ('the' and the next are among 101-112).
    seen = {r["word_id"] for r in con.execute("SELECT word_id FROM spelling_attempts WHERE user_id=1")}
    unseen = con.execute(
        "SELECT word FROM words WHERE list_id=3 AND id NOT IN (%s) ORDER BY position LIMIT 1"
        % ",".join(map(str, seen))
    ).fetchone()["word"]
    assert focus == unseen
    assert len(plan.word_ids) == len(set(plan.word_ids))
    assert count(con, "spelling_focus", "user_id=1") == 1


def test_new_child_after_migration_gets_baseline(old_db):
    database.init_db()
    from services import spelling_progression as sp
    con = connect(old_db)
    plan = sp.plan_practice(3, con)
    assert plan.kind == "baseline" and len(plan.word_ids) == 10


def test_fresh_install_seed_sets_positions(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "fresh.db"))
    database.init_db()
    from seed.curriculum_words import seed
    with database.get_db() as db:
        seed(db)
        seed(db)  # idempotent
        lists = db.execute("SELECT year_group, position FROM word_lists ORDER BY position").fetchall()
        assert [(r["year_group"], r["position"]) for r in lists] == [(1, 1), (3, 2), (5, 3)]
        words = db.execute(
            "SELECT word FROM words w JOIN word_lists l ON l.id=w.list_id WHERE l.year_group=1 ORDER BY w.position"
        ).fetchall()
        assert [r["word"] for r in words][:3] == ["the", "a", "do"]
        assert db.execute("SELECT COUNT(*) FROM words WHERE position=0").fetchone()[0] == 0

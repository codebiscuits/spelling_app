"""Mastery trophies: one per word list and one per times table 2 to 12."""
import re

from services.arithmetic_facts import FACTORS, FACTS
from services.gamification import (
    award_arithmetic_mastery_trophies,
    award_spelling_mastery_trophies,
    table_fact_keys,
)
from database import SCHEMA
from tests.conftest import (
    app_db, make_list, make_user, make_words, run_full_test, setup_practice_list,
)
from tests.test_arithmetic_flow import finish, play, right


def master(db, uid, subject, keys):
    for k in keys:
        db.execute(
            "INSERT OR IGNORE INTO first_mastered (user_id, subject, item_key, mastered_at) "
            "VALUES (?,?,?,'2025-01-01T00:00:00+00:00')",
            (uid, subject, str(k)),
        )
    db.commit()


def trophy_rows(db, uid, subject):
    return [r["group_key"] for r in db.execute(
        "SELECT group_key FROM mastery_trophies WHERE user_id=? AND subject=? ORDER BY group_key",
        (uid, subject)).fetchall()]


# ── Table rule ─────────────────────────────────────────────────────────────

def test_table_trophy_needs_every_multiplication_and_division_of_that_table():
    keys = set(table_fact_keys(3))
    assert {"m:3x7", "m:7x3", "d:21/3", "d:21/7", "m:3x3", "d:9/3"} <= keys
    assert len(keys) == 42                       # 10 pairs of four, plus the square (two)
    assert "m:4x5" not in keys and "d:20/4" not in keys
    # the 2 trophy includes 24 / 12 (answer 2) and the 10 trophy includes 20 / 2
    assert "d:24/12" in table_fact_keys(2) and "d:20/2" in table_fact_keys(10)
    assert set(FACTORS) == set(range(2, 13))
    assert all(set(table_fact_keys(t)) <= set(FACTS) for t in FACTORS)


def test_a_table_trophy_is_not_won_while_one_direction_is_missing(db):
    uid = make_user(db)
    keys = table_fact_keys(3)
    master(db, uid, "arithmetic", [k for k in keys if k != "d:21/3"])
    assert award_arithmetic_mastery_trophies(uid, db) == []
    assert trophy_rows(db, uid, "arithmetic") == []
    master(db, uid, "arithmetic", ["d:21/3"])
    assert award_arithmetic_mastery_trophies(uid, db) == [{"group_key": "3", "label": "3"}]
    assert award_arithmetic_mastery_trophies(uid, db) == []       # once only


def test_two_and_ten_are_separate_trophies_and_one_fact_can_help_two(db):
    uid = make_user(db)
    master(db, uid, "arithmetic", table_fact_keys(2))
    assert [t["label"] for t in award_arithmetic_mastery_trophies(uid, db)] == ["2"]
    master(db, uid, "arithmetic", table_fact_keys(10))
    assert [t["label"] for t in award_arithmetic_mastery_trophies(uid, db)] == ["10"]


def test_all_eleven_table_trophies(db):
    uid = make_user(db)
    master(db, uid, "arithmetic", list(FACTS))
    assert len(award_arithmetic_mastery_trophies(uid, db)) == 11
    assert trophy_rows(db, uid, "arithmetic") == sorted(str(t) for t in FACTORS)


def test_spelling_mastery_does_not_count_for_tables(db):
    uid = make_user(db)
    master(db, uid, "spelling", list(FACTS))
    assert award_arithmetic_mastery_trophies(uid, db) == []


# ── List rule ──────────────────────────────────────────────────────────────

def test_list_trophy_needs_every_word_mastered(db):
    uid = make_user(db)
    lid = make_list(db, "Year 3–4")
    ids = make_words(db, lid, ["a", "b", "c"])
    master(db, uid, "spelling", ids[:2])
    assert award_spelling_mastery_trophies(uid, db) == []
    master(db, uid, "spelling", ids[2:])
    assert award_spelling_mastery_trophies(uid, db) == [{"group_key": str(lid), "label": "Year 3–4"}]
    assert award_spelling_mastery_trophies(uid, db) == []


def test_other_lists_and_children_do_not_count(db):
    uid, other = make_user(db), make_user(db, "Bob")
    l1, l2 = make_list(db, "One"), make_list(db, "Two")
    w1 = make_words(db, l1, ["a"])
    make_words(db, l2, ["b"])
    master(db, other, "spelling", w1)
    master(db, uid, "arithmetic", w1)            # wrong subject
    assert award_spelling_mastery_trophies(uid, db) == []
    master(db, uid, "spelling", w1)
    assert [t["label"] for t in award_spelling_mastery_trophies(uid, db)] == ["One"]


def test_empty_list_never_wins_a_trophy(db):
    uid = make_user(db)
    make_list(db, "Empty")
    assert award_spelling_mastery_trophies(uid, db) == []


def test_trophy_stays_won_when_a_word_is_added_later(db):
    uid = make_user(db)
    lid = make_list(db, "One")
    ids = make_words(db, lid, ["a"])
    master(db, uid, "spelling", ids)
    award_spelling_mastery_trophies(uid, db)
    make_words(db, lid, ["new"])
    assert award_spelling_mastery_trophies(uid, db) == []
    assert trophy_rows(db, uid, "spelling") == [str(lid)]


def test_schema_is_additive_and_repeatable(db):
    db.executescript(SCHEMA)                    # a second run changes nothing
    cols = [r["name"] for r in db.execute("PRAGMA table_info(mastery_trophies)")]
    assert cols == ["user_id", "subject", "group_key", "earned_at", "silent"]
    uid = make_user(db)
    db.execute("INSERT INTO start_trophies (user_id, subject, group_id, earned_at) VALUES (?,?,?,?)",
               (uid, "spelling", 1, "2025-01-01"))
    db.executescript(SCHEMA)
    assert db.execute("SELECT COUNT(*) FROM start_trophies").fetchone()[0] == 1


# ── Results pages ──────────────────────────────────────────────────────────

def test_spelling_results_show_trophy_banner_once(child_client):
    words = [f"word{c}" for c in "abcdefghij"]
    lid, ids = setup_practice_list(child_client.child_id, words, name="Year 3–4")
    with app_db() as db:
        master(db, child_client.child_id, "spelling", ids.values())
    resp = run_full_test(child_client, lambda w: w)
    assert "Trophy won: you've mastered Year 3–4!" in resp.text
    assert "You've started Year 3–4!" in resp.text
    assert "trophy-svg" in resp.text
    resp2 = run_full_test(child_client, lambda w: w)
    assert "Trophy won" not in resp2.text
    with app_db() as db:
        assert trophy_rows(db, child_client.child_id, "spelling") == [str(lid)]


def test_arithmetic_results_show_trophy_banner_and_award_is_non_silent(child_client):
    with app_db() as db:
        master(db, child_client.child_id, "arithmetic", table_fact_keys(5))
    play(child_client, right)
    resp = finish(child_client)
    assert "Trophy won: you've mastered the 5 times table!" in resp.text
    assert "You've started the 2 and 10 times tables!" in resp.text
    with app_db() as db:
        row = db.execute("SELECT silent FROM mastery_trophies WHERE subject='arithmetic'").fetchone()
    assert row["silent"] == 0
    play(child_client, right)
    assert "Trophy won" not in finish(child_client).text


def test_a_spelling_results_page_checks_only_spelling_trophies(child_client):
    with app_db() as db:
        master(db, child_client.child_id, "arithmetic", table_fact_keys(5))
    setup_practice_list(child_client.child_id, [f"word{c}" for c in "abcdefghij"])
    resp = run_full_test(child_client, lambda w: w)
    assert "times table" not in resp.text.split("Practice Complete")[1].split("<table")[0]
    with app_db() as db:
        assert trophy_rows(db, child_client.child_id, "arithmetic") == []


def test_trophies_never_unlock_a_game(child_client):
    with app_db() as db:
        master(db, child_client.child_id, "arithmetic", list(FACTS))
    play(child_client, right)
    resp = finish(child_client)
    assert resp.text.count('class="award-banner award-trophy"') == 11
    assert "A new game is ready!" not in resp.text or "Badge earned" in resp.text
    with app_db() as db:
        sources = [r["source"] for r in db.execute("SELECT source FROM user_game_unlocks")]
    assert "trophy" not in sources


# ── Cabinet and admin ──────────────────────────────────────────────────────

def test_cabinet_shows_every_slot_with_titles_and_unique_ids(child_client):
    with app_db() as db:
        lists = db.execute("SELECT id, name FROM word_lists ORDER BY position, id").fetchall()
        db.execute("INSERT INTO mastery_trophies (user_id, subject, group_key, earned_at) VALUES (?,?,?,?)",
                   (child_client.child_id, "arithmetic", "7", "2026-10-12T09:00:00+00:00"))
        db.execute("INSERT INTO mastery_trophies (user_id, subject, group_key, earned_at) VALUES (?,?,?,?)",
                   (child_client.child_id, "spelling", str(lists[1]["id"]), "2026-10-13T09:00:00+00:00"))
    page = child_client.get("/child/dashboard").text
    assert "Trophy cabinet" in page and "Times tables" in page and "Spelling lists" in page
    assert "7 times table: won on 12 Oct" in page
    assert "2 times table: not won yet" in page
    assert f"{lists[1]['name']}: won on 13 Oct" in page
    assert f"{lists[0]['name']}: not won yet" in page
    assert len(lists) == 3
    assert page.count('class="shelf-slot"') == 11 + 3
    # tables in number order
    order = [int(m) for m in re.findall(r'<li class="shelf-slot" title="(\d+) times table', page)]
    assert order == list(range(2, 13))
    ids = re.findall(r'<linearGradient id="(tr\d+b)"', page)
    assert len(ids) == len(set(ids))
    assert "/static/img/trophy.svg" not in page
    assert "of 15 discovered" in page


def test_start_records_are_not_shown_as_trophies_on_the_dashboard(child_client):
    lid, _ = setup_practice_list(child_client.child_id, ["aa"], name="Mine")
    with app_db() as db:
        db.execute("INSERT INTO start_trophies (user_id, subject, group_id, earned_at, silent) "
                   "VALUES (?,?,?,?,0)", (child_client.child_id, "spelling", lid, "2025-01-01"))
        db.execute("INSERT INTO start_trophies (user_id, subject, group_id, earned_at, silent) "
                   "VALUES (?,?,?,?,0)", (child_client.child_id, "arithmetic", 1, "2025-01-01"))
    page = child_client.get("/child/dashboard").text
    assert "Mine: not won yet" in page
    assert "Started" not in page
    assert "trophy-won" not in page


def test_trophy_macro_looks_and_wording(child_client):
    from templates_env import templates
    tpl = templates.env.from_string(
        '{% from "_trophy.html" import trophy %}'
        '{{ trophy("7", "table", true, 90, "7 times table") }}'
        '{{ trophy("Year 3–4", "list", true, 90, "Year 3–4") }}'
        '{{ trophy("12", "table", false, 90, "12 times table: not won yet") }}')
    out = tpl.render()
    assert out.count("<svg") == 3
    assert "—" not in out
    assert "var(--" not in out                   # metal colours are fixed, not palette colours
    assert "textLength" in out
    assert "test" not in re.sub(r"<[^>]+>", " ", out).lower()


def test_admin_child_detail_lists_mastery_trophies(admin_client, child_client):
    with app_db() as db:
        db.execute("INSERT INTO mastery_trophies (user_id, subject, group_key, earned_at) VALUES (?,?,?,?)",
                   (child_client.child_id, "arithmetic", "9", "2026-10-12T09:00:00+00:00"))
        lid = db.execute("SELECT id FROM word_lists ORDER BY position, id").fetchone()["id"]
        db.execute("INSERT INTO mastery_trophies (user_id, subject, group_key, earned_at) VALUES (?,?,?,?)",
                   (child_client.child_id, "spelling", str(lid), "2026-10-13T09:00:00+00:00"))
    admin_client.cookies.clear()
    from tests.conftest import login, TEST_PASSWORD
    login(admin_client, "admin", TEST_PASSWORD)
    page = admin_client.get(f"/admin/children/{child_client.child_id}").text
    assert "9 times table" in page and "Spelling list" in page

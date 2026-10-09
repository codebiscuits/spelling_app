from datetime import datetime, timezone

from services.gamification import (
    award_session_badge,
    award_start_trophies,
    record_mastery_and_medals,
)
from tests.conftest import make_user, make_list, make_words, make_session, record_attempt


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def badge_count(db, uid):
    return db.execute(
        "SELECT COUNT(*) AS c FROM test_badges WHERE user_id=?", (uid,)
    ).fetchone()["c"]


def new_session(db, uid, score):
    lid = make_list(db)
    return make_session(db, uid, lid, score=score)


# ── Badge: score >= 16, at most one per Europe/London day ──────────────────

def test_badge_awarded_at_threshold(db):
    uid = make_user(db)
    sid = new_session(db, uid, 16)
    assert award_session_badge(uid, sid, 16, db, now=utc(2026, 3, 2, 10)) is True
    assert badge_count(db, uid) == 1


def test_badge_not_awarded_below_threshold(db):
    uid = make_user(db)
    sid = new_session(db, uid, 15)
    assert award_session_badge(uid, sid, 15, db, now=utc(2026, 3, 2, 10)) is False
    assert badge_count(db, uid) == 0


def test_second_qualifying_practice_same_day_earns_no_second_badge(db):
    uid = make_user(db)
    first = new_session(db, uid, 18)
    second = new_session(db, uid, 20)
    assert award_session_badge(uid, first, 18, db, now=utc(2026, 3, 2, 8)) is True
    assert award_session_badge(uid, second, 20, db, now=utc(2026, 3, 2, 17)) is False
    assert badge_count(db, uid) == 1


def test_badge_is_earned_by_first_qualifying_practice_of_the_day(db):
    uid = make_user(db)
    low = new_session(db, uid, 12)
    good = new_session(db, uid, 17)
    assert award_session_badge(uid, low, 12, db, now=utc(2026, 3, 2, 8)) is False
    assert award_session_badge(uid, good, 17, db, now=utc(2026, 3, 2, 9)) is True


def test_a_new_day_allows_a_new_badge(db):
    uid = make_user(db)
    a = new_session(db, uid, 18)
    b = new_session(db, uid, 18)
    assert award_session_badge(uid, a, 18, db, now=utc(2026, 3, 2, 10)) is True
    assert award_session_badge(uid, b, 18, db, now=utc(2026, 3, 3, 10)) is True
    assert badge_count(db, uid) == 2


def test_badges_are_counted_per_child(db):
    alice, bob = make_user(db, "Alice"), make_user(db, "Bob")
    a = new_session(db, alice, 18)
    b = new_session(db, bob, 18)
    assert award_session_badge(alice, a, 18, db, now=utc(2026, 3, 2, 10)) is True
    assert award_session_badge(bob, b, 18, db, now=utc(2026, 3, 2, 10)) is True


def test_london_day_in_summer_differs_from_utc_day(db):
    """23:30 UTC on 1 June is 00:30 BST on 2 June: a new London day, even
    though the UTC date is the same as an earlier badge's."""
    uid = make_user(db)
    a = new_session(db, uid, 18)
    b = new_session(db, uid, 18)
    assert award_session_badge(uid, a, 18, db, now=utc(2026, 6, 1, 12)) is True
    assert award_session_badge(uid, b, 18, db, now=utc(2026, 6, 1, 23, 30)) is True
    assert badge_count(db, uid) == 2


def test_two_utc_days_can_be_one_london_day_in_summer(db):
    """22:30 UTC on 1 June is 23:30 BST; 00:10 UTC on 2 June is 01:10 BST.
    These are two London days. But 23:10 UTC and 23:50 UTC on 1 June are
    00:10 and 00:50 BST on 2 June: one London day, so one badge."""
    uid = make_user(db)
    a = new_session(db, uid, 18)
    b = new_session(db, uid, 18)
    assert award_session_badge(uid, a, 18, db, now=utc(2026, 6, 1, 23, 10)) is True
    assert award_session_badge(uid, b, 18, db, now=utc(2026, 6, 1, 23, 50)) is False


def test_winter_london_day_matches_utc_day(db):
    uid = make_user(db)
    a = new_session(db, uid, 18)
    b = new_session(db, uid, 18)
    assert award_session_badge(uid, a, 18, db, now=utc(2026, 1, 10, 23, 30)) is True
    assert award_session_badge(uid, b, 18, db, now=utc(2026, 1, 11, 0, 30)) is True


def test_old_badge_rows_count_as_that_days_badge(db):
    uid = make_user(db)
    old = new_session(db, uid, 18)
    db.execute(
        "INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)",
        (uid, old, "2026-03-02T07:00:00+00:00"),
    )
    new = new_session(db, uid, 19)
    assert award_session_badge(uid, new, 19, db, now=utc(2026, 3, 2, 15)) is False


# ── Medals: one per ten distinct words first mastered ──────────────────────

def master(db, uid, wid, sid, times=3, correct=1):
    for _ in range(times):
        record_attempt(db, uid, wid, sid, 1, correct)


def test_no_medal_before_ten_mastered_words(db):
    uid = make_user(db)
    lid = make_list(db)
    ids = make_words(db, lid, [f"w{i}" for i in range(12)])
    sid = make_session(db, uid, lid)
    for wid in ids[:9]:
        master(db, uid, wid, sid)
    assert record_mastery_and_medals(uid, db) == []


def test_medal_at_ten_and_twenty(db):
    uid = make_user(db)
    lid = make_list(db)
    ids = make_words(db, lid, [f"w{i}" for i in range(25)])
    sid = make_session(db, uid, lid)
    for wid in ids[:10]:
        master(db, uid, wid, sid)
    assert record_mastery_and_medals(uid, db) == [10]
    assert record_mastery_and_medals(uid, db) == []  # not awarded twice
    for wid in ids[10:20]:
        master(db, uid, wid, sid)
    assert record_mastery_and_medals(uid, db) == [20]


def test_mastery_needs_three_in_a_row_latest(db):
    uid = make_user(db)
    lid = make_list(db)
    ids = make_words(db, lid, [f"w{i}" for i in range(10)])
    sid = make_session(db, uid, lid)
    for wid in ids:
        master(db, uid, wid, sid, times=2)  # only two correct
    assert record_mastery_and_medals(uid, db) == []


def test_remastering_a_forgotten_word_does_not_count_again(db):
    uid = make_user(db)
    lid = make_list(db)
    ids = make_words(db, lid, [f"w{i}" for i in range(11)])
    sid = make_session(db, uid, lid)
    for wid in ids[:9]:
        master(db, uid, wid, sid)
    master(db, uid, ids[9], sid)
    assert record_mastery_and_medals(uid, db) == [10]
    # Word 0 slips, then is mastered again
    record_attempt(db, uid, ids[0], sid, 1, 0)
    assert record_mastery_and_medals(uid, db) == []
    master(db, uid, ids[0], sid)
    assert record_mastery_and_medals(uid, db) == []
    count = db.execute(
        "SELECT COUNT(*) AS c FROM first_mastered WHERE user_id=?", (uid,)
    ).fetchone()["c"]
    assert count == 10
    # An eleventh distinct word is the only thing that moves the count
    master(db, uid, ids[10], sid)
    assert record_mastery_and_medals(uid, db) == []


def test_top_up_attempts_never_master_a_word(db):
    uid = make_user(db)
    lid = make_list(db)
    ids = make_words(db, lid, [f"w{i}" for i in range(10)])
    sid = make_session(db, uid, lid)
    for wid in ids:
        for _ in range(3):
            record_attempt(db, uid, wid, sid, attempt_number=3, correct=1)
    assert record_mastery_and_medals(uid, db) == []


# ── Trophies: one per list at the first ordinary first attempt ─────────────

def test_trophy_at_first_attempt_even_if_wrong(db):
    uid = make_user(db)
    lid = make_list(db, "Year A")
    (wid,) = make_words(db, lid, ["cat"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wid, sid, 1, correct=0)
    assert award_start_trophies(uid, db) == ["Year A"]
    assert award_start_trophies(uid, db) == []


def test_no_trophy_for_a_list_never_attempted_or_top_up_only(db):
    uid = make_user(db)
    l1 = make_list(db, "One")
    l2 = make_list(db, "Two")
    make_words(db, l1, ["cat"])
    (w2,) = make_words(db, l2, ["dog"])
    sid = make_session(db, uid, l1)
    record_attempt(db, uid, w2, sid, attempt_number=3, correct=1)
    assert award_start_trophies(uid, db) == []


def test_one_trophy_per_list_in_the_order_started(db):
    uid = make_user(db)
    l1 = make_list(db, "One")
    l2 = make_list(db, "Two")
    (w1,) = make_words(db, l1, ["cat"])
    (w2,) = make_words(db, l2, ["dog"])
    sid = make_session(db, uid, l1)
    record_attempt(db, uid, w2, sid, 1, 1)
    record_attempt(db, uid, w1, sid, 1, 1)
    assert award_start_trophies(uid, db) == ["Two", "One"]

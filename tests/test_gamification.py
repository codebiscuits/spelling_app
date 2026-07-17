from services.gamification import award_session_badge, check_and_award
from tests.conftest import make_user, make_list, make_words, make_session, record_attempt


def badge_count(db, uid):
    return db.execute(
        "SELECT COUNT(*) AS c FROM test_badges WHERE user_id=?", (uid,)
    ).fetchone()["c"]


# ── Badge (session score >= 16) ────────────────────────────────────────────

def test_badge_awarded_at_threshold(db):
    uid = make_user(db)
    lid = make_list(db)
    sid = make_session(db, uid, lid, score=16)
    assert award_session_badge(uid, sid, session_score=16, db=db) is True
    assert badge_count(db, uid) == 1


def test_badge_awarded_above_threshold(db):
    uid = make_user(db)
    lid = make_list(db)
    sid = make_session(db, uid, lid, score=20)
    assert award_session_badge(uid, sid, session_score=20, db=db) is True


def test_badge_not_awarded_below_threshold(db):
    uid = make_user(db)
    lid = make_list(db)
    sid = make_session(db, uid, lid, score=15)
    assert award_session_badge(uid, sid, session_score=15, db=db) is False
    assert badge_count(db, uid) == 0


def test_badge_can_be_awarded_multiple_times(db):
    uid = make_user(db)
    lid = make_list(db)
    make_words(db, lid, ["cat"])
    for _ in range(3):
        sid = make_session(db, uid, lid, score=16)
        assert award_session_badge(uid, sid, session_score=16, db=db) is True
    assert badge_count(db, uid) == 3


# ── Medal (>= 50% of list words first-try correct) ────────────────────────

def test_medal_awarded_at_50_percent(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["medal_awarded"] is True


def test_medal_not_awarded_below_50_percent(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog", "fish"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["medal_awarded"] is False


def test_medal_not_awarded_twice(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog"])

    sid1 = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid1, attempt_number=1, correct=1)
    r1 = check_and_award(uid, lid, db=db)
    assert r1["medal_awarded"] is True

    sid2 = make_session(db, uid, lid)
    r2 = check_and_award(uid, lid, db=db)
    assert r2["medal_awarded"] is False


def test_medal_threshold_rounds_up_on_odd_counts(db):
    """3-word list: ceil(0.5 * 3) = 2, so 1 first-try word is not enough
    but 2 are."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog", "fish"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    assert check_and_award(uid, lid, db=db)["medal_awarded"] is False
    record_attempt(db, uid, wids[1], sid, attempt_number=1, correct=1)
    assert check_and_award(uid, lid, db=db)["medal_awarded"] is True


def test_medal_ignores_second_try_correct(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid, attempt_number=2, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["medal_awarded"] is False


def test_medal_counts_across_sessions(db):
    """First-try correct attempts from different sessions all count toward medal."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog", "fish", "bird"])

    sid1 = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid1, attempt_number=1, correct=1)

    sid2 = make_session(db, uid, lid)
    record_attempt(db, uid, wids[1], sid2, attempt_number=1, correct=1)

    result = check_and_award(uid, lid, db=db)
    assert result["medal_awarded"] is True


# ── Trophy (>= 95% first-try + all remaining second-try) ──────────────────

def test_trophy_awarded_all_first_try(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog", "fish", "bird", "frog",
                                "tree", "book", "cake", "rain", "snow"])
    sid = make_session(db, uid, lid)
    for wid in wids:
        record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["trophy_awarded"] is True


def test_trophy_awarded_95_percent_first_try_rest_second_try(db):
    """19/20 first-try, last word correct on second try → trophy."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(20)])
    sid = make_session(db, uid, lid)
    for wid in wids[:-1]:
        record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)
    record_attempt(db, uid, wids[-1], sid, attempt_number=2, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["trophy_awarded"] is True


def test_trophy_not_awarded_if_remaining_word_not_second_try_correct(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(20)])
    sid = make_session(db, uid, lid)
    for wid in wids[:-1]:
        record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)
    # Last word never attempted — no second-try correct
    result = check_and_award(uid, lid, db=db)
    assert result["trophy_awarded"] is False


def test_trophy_not_awarded_below_95_percent_first_try(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(20)])
    sid = make_session(db, uid, lid)
    # Only 18/20 first-try correct (90%)
    for wid in wids[:18]:
        record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)
    for wid in wids[18:]:
        record_attempt(db, uid, wid, sid, attempt_number=2, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["trophy_awarded"] is False


def test_trophy_not_awarded_twice(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog"])
    sid1 = make_session(db, uid, lid)
    for wid in wids:
        record_attempt(db, uid, wid, sid1, attempt_number=1, correct=1)
    r1 = check_and_award(uid, lid, db=db)
    assert r1["trophy_awarded"] is True

    sid2 = make_session(db, uid, lid)
    r2 = check_and_award(uid, lid, db=db)
    assert r2["trophy_awarded"] is False


def test_trophy_second_try_from_earlier_session_counts(db):
    """The qualifying second-try-correct can come from any past session."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(20)])

    sid1 = make_session(db, uid, lid)
    record_attempt(db, uid, wids[-1], sid1, attempt_number=1, correct=0)
    record_attempt(db, uid, wids[-1], sid1, attempt_number=2, correct=1)

    sid2 = make_session(db, uid, lid)
    for wid in wids[:-1]:
        record_attempt(db, uid, wid, sid2, attempt_number=1, correct=1)

    result = check_and_award(uid, lid, db=db)
    assert result["trophy_awarded"] is True


# ── List unlock on trophy ──────────────────────────────────────────────────

def test_trophy_unlocks_next_year_group(db):
    uid = make_user(db)
    lid1 = make_list(db, year_group=1)
    lid3 = make_list(db, year_group=3)
    wids = make_words(db, lid1, ["cat", "dog"])
    sid = make_session(db, uid, lid1)
    for wid in wids:
        record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid1, db=db)
    assert result["trophy_awarded"] is True
    assert lid3 in result["lists_unlocked"]


def test_trophy_year_group_3_unlocks_year_group_5(db):
    uid = make_user(db)
    lid3 = make_list(db, year_group=3)
    lid5 = make_list(db, year_group=5)
    wids = make_words(db, lid3, ["cat"])
    sid = make_session(db, uid, lid3)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid3, db=db)
    assert result["trophy_awarded"] is True
    assert lid5 in result["lists_unlocked"]


def test_trophy_unlocks_all_lists_in_next_year_group(db):
    uid = make_user(db)
    lid1 = make_list(db, "Year 1 list", year_group=1)
    lid3a = make_list(db, "Year 3 list A", year_group=3)
    lid3b = make_list(db, "Year 3 list B", year_group=3)
    wids = make_words(db, lid1, ["cat"])
    sid = make_session(db, uid, lid1)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid1, db=db)
    assert sorted(result["lists_unlocked"]) == sorted([lid3a, lid3b])


def test_trophy_year_group_5_unlocks_nothing(db):
    """There is no year group above 5–6."""
    uid = make_user(db)
    lid5 = make_list(db, year_group=5)
    wids = make_words(db, lid5, ["cat"])
    sid = make_session(db, uid, lid5)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid5, db=db)
    assert result["trophy_awarded"] is True
    assert result["lists_unlocked"] == []


def test_already_unlocked_list_not_reported_as_newly_unlocked(db):
    """If the admin pre-unlocked the next list, the trophy should not
    announce it as a new unlock."""
    uid = make_user(db)
    lid1 = make_list(db, year_group=1)
    lid3 = make_list(db, year_group=3)
    db.execute(
        "INSERT INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,'2025-01-01')",
        (uid, lid3),
    )
    db.commit()
    wids = make_words(db, lid1, ["cat"])
    sid = make_session(db, uid, lid1)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid1, db=db)
    assert result["trophy_awarded"] is True
    assert result["lists_unlocked"] == []


def test_trophy_no_unlock_for_list_without_year_group(db):
    uid = make_user(db)
    lid = make_list(db, year_group=None)
    wids = make_words(db, lid, ["cat"])
    sid = make_session(db, uid, lid)
    record_attempt(db, uid, wids[0], sid, attempt_number=1, correct=1)
    result = check_and_award(uid, lid, db=db)
    assert result["trophy_awarded"] is True
    assert result["lists_unlocked"] == []


def test_no_medal_or_trophy_for_empty_list(db):
    """Badge is still awarded by score alone, but medal/trophy require words."""
    uid = make_user(db)
    lid = make_list(db)
    sid = make_session(db, uid, lid)
    result = check_and_award(uid, lid, db=db)
    assert result["medal_awarded"] is False
    assert result["trophy_awarded"] is False

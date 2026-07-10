from services.word_selection import select_words
from tests.conftest import make_user, make_list, make_words, make_session, record_attempt


def test_returns_empty_for_no_lists(db):
    uid = make_user(db)
    assert select_words(uid, [], 10, db) == []


def test_returns_empty_for_empty_list(db):
    uid = make_user(db)
    lid = make_list(db)
    assert select_words(uid, [lid], 10, db) == []


def test_returns_all_words_when_fewer_than_n(db):
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, ["cat", "dog", "fish"])
    result = select_words(uid, [lid], 10, db)
    assert sorted(result) == sorted(wids)


def test_returns_exactly_n_words(db):
    uid = make_user(db)
    lid = make_list(db)
    make_words(db, lid, [f"word{i}" for i in range(20)])
    result = select_words(uid, [lid], 10, db)
    assert len(result) == 10


def test_returns_only_words_from_the_list(db):
    uid = make_user(db)
    lid1 = make_list(db, "List 1")
    lid2 = make_list(db, "List 2")
    wids1 = make_words(db, lid1, [f"a{i}" for i in range(15)])
    make_words(db, lid2, [f"b{i}" for i in range(15)])
    result = select_words(uid, [lid1], 10, db)
    assert all(wid in wids1 for wid in result)


def test_samples_across_multiple_lists(db):
    uid = make_user(db)
    lid1 = make_list(db, "List 1")
    lid2 = make_list(db, "List 2")
    wids1 = make_words(db, lid1, ["a1", "a2"])
    wids2 = make_words(db, lid2, ["b1", "b2"])
    result = select_words(uid, [lid1, lid2], 10, db)
    assert sorted(result) == sorted(wids1 + wids2)


def test_no_duplicate_words_in_selection(db):
    uid = make_user(db)
    lid = make_list(db)
    make_words(db, lid, [f"word{i}" for i in range(20)])
    result = select_words(uid, [lid], 10, db)
    assert len(result) == len(set(result))


def test_struggled_words_selected_more_often(db):
    """Words with a poor history should appear more often than well-known ones.
    Run many trials and check the struggling word appears significantly more."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(10)])
    hard_word = wids[0]
    easy_words = wids[1:]

    # Give hard_word a poor history (always wrong)
    for i in range(5):
        sid = make_session(db, uid, lid)
        record_attempt(db, uid, hard_word, sid, attempt_number=1, correct=0)

    # Give easy_words a good history (always correct first try)
    for wid in easy_words:
        for i in range(5):
            sid = make_session(db, uid, lid)
            record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)

    # Run 200 trials selecting 1 word at a time
    hard_count = sum(
        1 for _ in range(200) if select_words(uid, [lid], 1, db)[0] == hard_word
    )
    # Hard word should appear far more than the ~10% random baseline
    assert hard_count > 50


def test_unseen_words_weighted_between_hard_and_easy(db):
    """An unseen word (neutral weight) should be picked more often than a
    mastered word but less often than a consistently failed word."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(3)] + [f"pad{i}" for i in range(7)])
    hard, easy, unseen = wids[0], wids[1], wids[2]

    for i in range(5):
        sid = make_session(db, uid, lid)
        record_attempt(db, uid, hard, sid, attempt_number=1, correct=0)
        record_attempt(db, uid, easy, sid, attempt_number=1, correct=1)

    counts = {hard: 0, easy: 0, unseen: 0}
    for _ in range(500):
        picked = select_words(uid, [lid], 1, db)[0]
        if picked in counts:
            counts[picked] += 1

    assert counts[hard] > counts[unseen] > counts[easy]


def test_second_try_history_weighted_between_first_try_and_failure(db):
    """Second-try-correct (1 point) should rank between always-failed (0)
    and first-try-correct (2) in selection frequency."""
    uid = make_user(db)
    lid = make_list(db)
    wids = make_words(db, lid, [f"word{i}" for i in range(3)] + [f"pad{i}" for i in range(7)])
    failed, second_try, first_try = wids[0], wids[1], wids[2]

    for i in range(5):
        sid = make_session(db, uid, lid)
        record_attempt(db, uid, failed, sid, attempt_number=1, correct=0)
        record_attempt(db, uid, failed, sid, attempt_number=2, correct=0)
        record_attempt(db, uid, second_try, sid, attempt_number=1, correct=0)
        record_attempt(db, uid, second_try, sid, attempt_number=2, correct=1)
        record_attempt(db, uid, first_try, sid, attempt_number=1, correct=1)

    # Pad words get perfect history so they don't dominate
    for wid in wids[3:]:
        for i in range(5):
            sid = make_session(db, uid, lid)
            record_attempt(db, uid, wid, sid, attempt_number=1, correct=1)

    counts = {failed: 0, second_try: 0, first_try: 0}
    for _ in range(600):
        picked = select_words(uid, [lid], 1, db)[0]
        if picked in counts:
            counts[picked] += 1

    assert counts[failed] > counts[second_try] > counts[first_try]

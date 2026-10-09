"""Selection service: focus word, 1+5+4 practice shape, vacancies, lists."""
from services import spelling_progression as sp
from tests.conftest import make_session, make_user, record_attempt


def mk_list(db, name, words, position, year_group=None):
    """Create a list and words with explicit curriculum positions. Words are
    inserted in REVERSE of curriculum order so insertion order (id) and
    alphabetical order both disagree with the position order."""
    cur = db.execute(
        "INSERT INTO word_lists (name, year_group, position) VALUES (?,?,?)",
        (name, year_group, position),
    )
    lid = cur.lastrowid
    ids = {}
    for pos, w in reversed(list(enumerate(words, start=1))):
        ids[w] = db.execute(
            "INSERT INTO words (word, list_id, position) VALUES (?,?,?)", (w, lid, pos)
        ).lastrowid
    db.commit()
    return lid, ids


def unlock(db, uid, *list_ids):
    for lid in list_ids:
        db.execute(
            "INSERT INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,'2026-01-01')",
            (uid, lid),
        )
    db.commit()


class World:
    """One child, one session, helpers that record attempts in call order."""

    def __init__(self, db, words, extra=None):
        self.db = db
        self.uid = make_user(db)
        self.lid, self.ids = mk_list(db, "Main", words, 1)
        unlock(db, self.uid, self.lid)
        self.sid = make_session(db, self.uid, self.lid)

    def first(self, word, *results):
        """Record ordinary first attempts (1 right, 0 wrong), oldest first."""
        for r in results:
            record_attempt(self.db, self.uid, self.ids[word], self.sid, 1, r)

    def topup(self, word, correct=1):
        record_attempt(self.db, self.uid, self.ids[word], self.sid, 3, correct)

    def plan(self, **kw):
        return sp.plan_practice(self.uid, self.db, **kw)

    def names(self, word_ids):
        back = {v: k for k, v in self.ids.items()}
        return [back[i] for i in word_ids]


WORDS = [f"w{n:02d}" for n in range(1, 41)]
# curriculum order is w01..w40 but the helper inserts them in reverse, so id
# order is w40..w01 and neither id nor (for the reversed names below) the
# alphabet is the curriculum order.
ZIGZAG = ["zebra", "apple", "mango", "kiwi", "banana", "yak", "cherry", "xray", "date", "nut",
          "pear", "plum", "fig", "lime", "quince"]


# ── Baseline ───────────────────────────────────────────────────────────────

def test_baseline_is_ten_earliest_locked_words_in_curriculum_order(db):
    w = World(db, ZIGZAG)
    plan = w.plan()
    assert plan.kind == "baseline"
    assert plan.focus_id is None
    assert w.names(plan.word_ids) == ZIGZAG[:10]  # not alphabetical, not id order
    assert db.execute("SELECT COUNT(*) FROM spelling_focus").fetchone()[0] == 0


def test_baseline_applies_only_when_there_are_no_ordinary_attempts_at_all(db):
    w = World(db, ZIGZAG)
    w.topup("zebra")  # a top-up is not an ordinary attempt
    assert w.plan().kind == "baseline"
    w.first("zebra", 0)
    assert w.plan().kind == "normal"


def test_baseline_with_fewer_than_ten_words_returns_them_all(db):
    w = World(db, ZIGZAG[:4])
    assert w.names(w.plan().word_ids) == ZIGZAG[:4]


# ── Focus ──────────────────────────────────────────────────────────────────

def seen_baseline(w, n=10, results=(1,)):
    for word in ZIGZAG[:n]:
        w.first(word, *results)


def test_practice_after_baseline_introduces_next_locked_word_as_focus(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    plan = w.plan()
    assert w.names([plan.focus_id]) == [ZIGZAG[10]]  # 'pear', earliest locked
    assert plan.focus_id in plan.word_ids
    row = db.execute("SELECT * FROM spelling_focus WHERE user_id=?", (w.uid,)).fetchone()
    assert row["word_id"] == plan.focus_id and row["completed_at"] is None


def test_open_focus_stays_in_every_practice_until_three_in_a_row(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    focus = w.plan().focus_id
    name = w.names([focus])[0]
    for results in ([1], [1], [0], [1], [1]):  # 1,1,0,1,1 -> no run of three
        w.first(name, *results)
        plan = w.plan()
        assert plan.focus_id == focus and focus in plan.word_ids
    assert db.execute("SELECT COUNT(*) FROM spelling_focus").fetchone()[0] == 1


def test_focus_completes_after_three_consecutive_correct_then_next_word_introduced(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    first_focus = w.plan().focus_id
    name = w.names([first_focus])[0]
    w.first(name, 0, 1, 1, 1)
    sp.refresh_focus(w.uid, db)
    done = db.execute("SELECT completed_at FROM spelling_focus WHERE word_id=?", (first_focus,)).fetchone()
    assert done["completed_at"] is not None
    plan = w.plan()
    assert plan.focus_id != first_focus
    assert w.names([plan.focus_id]) == [ZIGZAG[11]]
    open_rows = db.execute(
        "SELECT COUNT(*) FROM spelling_focus WHERE user_id=? AND completed_at IS NULL", (w.uid,)
    ).fetchone()[0]
    assert open_rows == 1


def test_correct_attempts_before_the_focus_began_do_not_count(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    focus = w.plan().focus_id
    name = w.names([focus])[0]
    w.first(name, 1, 1)  # only two since it became focus
    assert w.plan().focus_id == focus


def test_top_ups_never_complete_a_focus(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    focus = w.plan().focus_id
    name = w.names([focus])[0]
    for _ in range(3):
        w.topup(name)
    assert w.plan().focus_id == focus


def test_second_attempts_never_complete_a_focus(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    focus = w.plan().focus_id
    for _ in range(3):
        record_attempt(db, w.uid, focus, w.sid, 2, 1)
    assert w.plan().focus_id == focus


def test_never_two_open_focus_rows(db):
    w = World(db, ZIGZAG)
    seen_baseline(w)
    for _ in range(5):
        w.plan()
    assert db.execute(
        "SELECT COUNT(*) FROM spelling_focus WHERE completed_at IS NULL"
    ).fetchone()[0] == 1


# ── Shape of a normal practice ─────────────────────────────────────────────

def build_mixed_world(db):
    """40 words: 20 seen. w01-w06 weak (6 attempts, mixed), w07-w14 mastered
    (3 correct) in staleness order, w15-w20 seen-not-mastered with 2 attempts."""
    w = World(db, WORDS)
    for n in range(1, 21):
        word = WORDS[n - 1]
        if n <= 6:
            w.first(word, 0, 1, 0, 1, 0, 1 if n % 2 else 0)
        elif n <= 14:
            w.first(word, 1, 1, 1)
        else:
            w.first(word, 0, 1)
    return w


def test_normal_practice_is_one_focus_five_weak_four_stale(db):
    w = build_mixed_world(db)
    plan = w.plan()
    names = w.names(plan.word_ids)
    assert len(names) == 10 and len(set(names)) == 10
    assert names[0] == "w21"  # focus: earliest locked word
    weak = names[1:6]
    stale = names[6:]
    assert all(n in WORDS[:6] for n in weak)       # weak eligible only
    assert stale == ["w07", "w08", "w09", "w10"]   # mastered, longest unpractised first


def test_focus_never_takes_a_weak_slot(db):
    w = build_mixed_world(db)
    # make the focus word itself the weakest eligible word
    plan = w.plan()
    focus_name = w.names([plan.focus_id])[0]
    w.first(focus_name, 0, 0, 0, 0, 0)
    plan2 = w.plan()
    assert plan2.focus_id == plan.focus_id
    assert plan2.word_ids.count(plan.focus_id) == 1
    assert len(plan2.word_ids) == 10
    weak_part = plan2.word_ids[1:6]
    assert plan.focus_id not in weak_part


def test_no_locked_word_and_no_focus_gives_six_weak_four_stale(db):
    w = World(db, WORDS[:20])
    for n in range(20):
        word = WORDS[n]
        if n < 8:
            w.first(word, 0, 1, 0, 1, 0, 0)   # weak eligible
        else:
            w.first(word, 1, 1, 1)             # mastered
    plan = w.plan()
    assert plan.focus_id is None
    assert db.execute("SELECT COUNT(*) FROM spelling_focus").fetchone()[0] == 0
    names = w.names(plan.word_ids)
    assert len(names) == 10 and len(set(names)) == 10
    assert sum(n in WORDS[:8] for n in names) == 6
    assert sum(n in WORDS[8:] for n in names) == 4


def test_weak_requires_five_ordinary_first_attempts(db):
    w = World(db, WORDS[:20])
    w.first("w01", 0, 0, 0, 0)         # four misses: not yet eligible
    w.first("w02", 0, 0, 0, 0, 0)      # five misses: eligible
    ordered = sp.curriculum_word_ids([w.lid], db)
    pools = sp.build_pools(sp.load_history(w.uid, db), ordered)
    assert w.names(pools.weak) == ["w02"]
    assert w.names(pools.other_seen) == ["w01"]


def test_weak_ranked_by_latest_five_accuracy_then_longest_since_practice(db):
    w = World(db, WORDS[:20])
    w.first("w01", 1, 1, 1, 1, 1, 0)   # latest five: 1,1,1,1,0 -> 0.8
    w.first("w02", 0, 0, 0, 1, 1)      # latest five: 0.4
    w.first("w03", 0, 1, 0, 1, 0)      # 0.4, practised later than w02
    w.first("w04", 1, 0, 0, 0, 0, 0)   # latest five all wrong -> 0.0
    ordered = sp.curriculum_word_ids([w.lid], db)
    pools = sp.build_pools(sp.load_history(w.uid, db), ordered)
    assert w.names(pools.weak) == ["w04", "w02", "w03", "w01"]


def test_stale_is_mastered_words_ordered_by_longest_since_appearance(db):
    w = World(db, WORDS[:20])
    for word in ("w05", "w03", "w09"):
        w.first(word, 1, 1, 1)
    # w05 appears again recently, so it is now the least stale
    w.first("w05", 1)
    ordered = sp.curriculum_word_ids([w.lid], db)
    pools = sp.build_pools(sp.load_history(w.uid, db), ordered)
    assert w.names(pools.stale) == ["w03", "w09", "w05"]


def test_mastered_word_with_first_try_error_returns_to_seen_not_mastered(db):
    w = World(db, WORDS[:20])
    w.first("w01", 1, 1, 1)
    ordered = sp.curriculum_word_ids([w.lid], db)
    hist = sp.load_history(w.uid, db)
    assert w.names(sp.build_pools(hist, ordered).stale) == ["w01"]
    w.first("w01", 0)
    hist = sp.load_history(w.uid, db)
    pools = sp.build_pools(hist, ordered)
    assert pools.stale == []
    assert w.names(pools.seen_not_mastered) == ["w01"]
    # and it needs three new correct answers in a row to be mastered again
    w.first("w01", 1, 1)
    assert not sp.is_mastered(sp.load_history(w.uid, db)[w.ids["w01"]])
    w.first("w01", 1)
    assert sp.is_mastered(sp.load_history(w.uid, db)[w.ids["w01"]])


# ── Vacancies ──────────────────────────────────────────────────────────────

def test_weak_vacancy_filled_from_other_seen_words_stalest_first_then_mastered(db):
    w = World(db, WORDS[:30])
    w.first("w01", 0, 0, 0, 0, 0)            # the only eligible weak word
    # not-yet-eligible seen words, w12 practised most recently
    for word in ("w10", "w11", "w12"):
        w.first(word, 0, 1)
    for word in ("w20", "w21", "w22", "w23", "w24", "w25", "w26"):
        w.first(word, 1, 1, 1)               # 7 mastered, w20 stalest
    plan = w.plan()
    names = w.names(plan.word_ids)
    assert names[0] == "w02"                 # the focus: earliest locked
    assert len(names) == 10 and len(set(names)) == 10
    # Stale slots take the four stalest mastered words. The weak slots hold
    # w01, then the vacancy takes the other seen-not-mastered words (w10,
    # w11, w12) before it touches the next mastered word (w24).
    assert set(names[2:6]) == {"w20", "w21", "w22", "w23"}
    assert names[1] == "w01"
    assert names[6:] == ["w10", "w11", "w12", "w24"]


def test_stale_vacancy_filled_from_other_seen_not_mastered_before_anything_else(db):
    w = World(db, WORDS[:30])
    for n in range(1, 8):
        w.first(WORDS[n - 1], 0, 0, 0, 0, 0)   # 7 weak eligible
    w.first("w20", 1, 1, 1)                     # 1 mastered
    plan = w.plan()
    names = w.names(plan.word_ids)
    assert len(names) == 9  # focus + 7 weak + 1 mastered: nothing else is seen
    assert "w08" in names   # the focus (earliest locked word)
    assert names.count("w20") == 1


def test_short_practice_is_never_padded_with_a_second_new_word(db):
    w = World(db, WORDS[:30])
    seen_words = WORDS[:3]
    for word in seen_words:
        w.first(word, 1, 0)
    names = w.names(w.plan().word_ids)
    assert sorted(names) == sorted(seen_words + ["w04"])


def test_no_word_twice_in_any_practice(db):
    w = build_mixed_world(db)
    for _ in range(5):
        ids = w.plan().word_ids
        assert len(ids) == len(set(ids))
        for wid in ids[1:]:
            record_attempt(db, w.uid, wid, w.sid, 1, 0)


def test_selection_is_deterministic(db):
    w = build_mixed_world(db)
    assert w.plan().word_ids == w.plan().word_ids


# ── Top-ups ────────────────────────────────────────────────────────────────

def test_top_up_attempts_do_not_change_pools_or_staleness(db):
    w = World(db, WORDS[:20])
    for word in ("w01", "w02", "w03"):
        w.first(word, 1, 1, 1)
    ordered = sp.curriculum_word_ids([w.lid], db)
    before = sp.build_pools(sp.load_history(w.uid, db), ordered)
    for word in ("w01", "w02", "w03"):
        w.topup(word, 1)
        w.topup(word, 0)
    after = sp.build_pools(sp.load_history(w.uid, db), ordered)
    assert before == after


def test_top_up_candidates_are_weak_then_stale_excluding_used_and_locked(db):
    w = World(db, WORDS[:20])
    w.first("w05", 0, 0, 0, 0, 0)       # weak
    w.first("w06", 1, 1, 1)             # mastered
    w.first("w07", 1, 0)                # seen, not eligible
    used = {w.ids["w05"]}
    cands = w.names(sp.topup_candidates(w.uid, db, exclude=used))
    assert cands == ["w06", "w07"]       # w05 excluded; locked words never offered
    assert w.names([sp.next_topup_word(w.uid, db, exclude=set())]) == ["w05"]
    assert sp.next_topup_word(w.uid, db, exclude={w.ids[x] for x in ("w05", "w06", "w07")}) is None


# ── Lists ──────────────────────────────────────────────────────────────────

def test_next_list_unlocks_only_when_every_word_has_been_introduced(db):
    w = World(db, WORDS[:12])
    l2, _ = mk_list(db, "Second", ["s1", "s2"], 2)
    seen = WORDS[:11]
    for word in seen:
        w.first(word, 1)
    w.plan()  # w12 becomes focus, but it has not appeared yet
    assert sp.available_list_ids(w.uid, db) == [w.lid]
    w.first("w12", 1)
    plan = w.plan()  # focus still open (one correct only); everything introduced
    assert sp.available_list_ids(w.uid, db) == [w.lid, l2]
    assert plan.focus_id == w.ids["w12"]


def test_next_list_is_after_the_furthest_list_and_lists_never_lock(db):
    uid = make_user(db)
    l1, _ = mk_list(db, "One", ["a1"], 1)
    l2, i2 = mk_list(db, "Two", ["b1", "b2"], 2)
    l3, _ = mk_list(db, "Three", ["c1"], 3)
    unlock(db, uid, l2)                  # starts at the second list only
    sid = make_session(db, uid, l2)
    for wid in i2.values():
        record_attempt(db, uid, wid, sid, 1, 1)
    sp.plan_practice(uid, db)
    assert sp.available_list_ids(uid, db) == [l2, l3]   # not l1, which is earlier
    sp.plan_practice(uid, db)
    assert l1 not in sp.available_list_ids(uid, db)
    assert l2 in sp.available_list_ids(uid, db)


def test_child_with_no_lists_gets_the_earliest_list_by_position(db):
    uid = make_user(db)
    mk_list(db, "Later", ["z"], 5)
    early, _ = mk_list(db, "Early", ["y"], 2)
    plan = sp.plan_practice(uid, db)
    assert sp.available_list_ids(uid, db) == [early]
    assert plan.kind == "baseline"


def test_words_of_a_newly_opened_list_join_the_locked_pool_in_order(db):
    w = World(db, ["a", "b", "c"])
    l2, ids2 = mk_list(db, "Two", ["x", "y"], 2)
    for word in ("a", "b", "c"):
        w.first(word, 1, 1, 1)
    plan = w.plan()
    assert plan.focus_id == ids2["x"]   # earliest word of the earliest new list
    assert l2 in sp.available_list_ids(w.uid, db)


def test_introduction_flag_is_true_only_in_the_session_of_first_appearance(db):
    w = World(db, ["a", "b"])
    other = make_session(db, w.uid, w.lid)
    assert sp.is_introduction(w.uid, w.ids["a"], w.sid, db)       # never seen
    w.first("a", 1)
    assert sp.is_introduction(w.uid, w.ids["a"], w.sid, db)       # same session
    assert not sp.is_introduction(w.uid, w.ids["a"], other, db)   # later session

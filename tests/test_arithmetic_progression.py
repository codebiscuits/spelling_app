"""Arithmetic facts, the table ladder, and the per-direction selector."""
import pytest

from services import arithmetic_progression as ap
from services.arithmetic_facts import (
    FACT_ORDER, FACTS, FAMILIES, FAMILY_ORDER, FAMILY_RUNG, LADDER,
    families_up_to_rung, facts_of_rung, get_fact, rung_name,
)
from tests.conftest import make_session, make_user


# ── Helpers ────────────────────────────────────────────────────────────────

class Child:
    def __init__(self, db):
        self.db = db
        self.uid = make_user(db)
        self.sid = make_session(db, self.uid, None)

    def attempt(self, key, correct=1, number=1, session=None):
        self.db.execute(
            """INSERT INTO arithmetic_attempts
               (timestamp, user_id, fact_key, correct, attempt_number, session_id)
               VALUES ('2026-01-01T00:00:00+00:00',?,?,?,?,?)""",
            (self.uid, key, correct, number, session or self.sid),
        )

    def secure(self, keys):
        for k in keys:
            for _ in range(3):
                self.attempt(k, 1)

    def practice(self, answer_fn=lambda key: 1):
        """Plan an ordinary practice and record a first attempt for each
        question. Returns the plan."""
        plan = ap.plan_practice(self.uid, self.db)
        for k in plan.fact_keys:
            self.attempt(k, answer_fn(k))
        self.db.commit()
        return plan

    def keys_of(self, family):
        return [f.key for f in FAMILIES[family]]


@pytest.fixture
def kid(db):
    return Child(db)


# ── Fact generation ────────────────────────────────────────────────────────

def test_full_ladder_counts():
    assert len(FAMILIES) == 66
    assert len(FACTS) == 242
    assert len(set(FACT_ORDER)) == 242


def test_rung_one_counts():
    fams = families_up_to_rung(1)
    assert len(fams) == 21
    assert sum(len(FAMILIES[f]) for f in fams) == 80
    assert sum(1 for f in fams if len(FAMILIES[f]) == 2) == 2   # 2x2 and 10x10
    assert len(facts_of_rung(1)) == 80


def test_no_multiplication_or_division_by_zero_or_one():
    for f in FACTS.values():
        assert f.left >= 2 and f.right >= 2 and f.answer >= 2
        assert 2 <= min(f.factors) and max(f.factors) <= 12


def test_keys_and_questions_are_stable():
    assert get_fact("m:3x4").text == "3 × 4" and get_fact("m:3x4").answer == 12
    assert get_fact("d:12/3").text == "12 ÷ 3" and get_fact("d:12/3").answer == 4
    assert [f.key for f in FAMILIES["f:3x4"]] == ["m:3x4", "m:4x3", "d:12/3", "d:12/4"]
    assert [f.key for f in FAMILIES["f:4x4"]] == ["m:4x4", "d:16/4"]


def test_a_direction_belongs_to_a_table_by_either_factor_or_quotient():
    assert get_fact("d:12/3").factors == {3, 4}
    assert get_fact("m:3x4").factors == {3, 4}
    assert "d:12/3" in facts_of_rung(3) and "d:12/3" in facts_of_rung(4)   # tables 4 and 3
    assert "d:12/3" not in facts_of_rung(1)


def test_ladder_order_and_family_rungs():
    assert LADDER == ((2, 10), (5,), (4,), (3,), (6,), (8,), (9,), (7,), (11,), (12,))
    assert rung_name(1) == "2 and 10" and rung_name(2) == "5"
    # a family belongs to the earliest rung at which a factor is active
    assert FAMILY_RUNG["f:2x3"] == 1       # 3x2: the 2 is active at rung 1
    assert FAMILY_RUNG["f:3x4"] == 3       # table 4 opens before table 3
    assert FAMILY_RUNG["f:3x5"] == 2
    assert "f:3x4" not in families_up_to_rung(1)
    assert "f:3x4" not in families_up_to_rung(2)
    assert "f:3x4" in families_up_to_rung(3)


def test_family_order_is_by_rung_then_smaller_factor():
    ranks = [FAMILY_RUNG[f] for f in FAMILY_ORDER]
    assert ranks == sorted(ranks)
    assert FAMILY_ORDER[:5] == ["f:2x2", "f:2x3", "f:2x4", "f:2x5", "f:2x6"]
    rung2 = [f for f in FAMILY_ORDER if FAMILY_RUNG[f] == 2]
    assert rung2[:3] == ["f:3x5", "f:4x5", "f:5x5"]


# ── Baseline ───────────────────────────────────────────────────────────────

def test_new_child_gets_a_baseline_of_ten_from_the_first_families(kid):
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.kind == "baseline"
    assert len(plan.fact_keys) == 10 == len(set(plan.fact_keys))
    assert set(plan.fact_keys) == set(
        kid.keys_of("f:2x2") + kid.keys_of("f:2x3") + kid.keys_of("f:2x4")
    )
    # deterministic, and starting rung 1 opens the first rung only
    assert ap.plan_practice(kid.uid, kid.db).fact_keys == plan.fact_keys
    assert ap.unlocked_rungs(kid.uid, kid.db) == [1]
    assert kid.db.execute("SELECT COUNT(*) FROM arithmetic_focus").fetchone()[0] == 0


def test_baseline_never_includes_half_a_family():
    keys = ap.baseline_keys(9)      # 2 + 4 + 4 does not fit: the last family is skipped
    assert len(keys) <= 9
    for fam in FAMILIES.values():
        got = [f.key in keys for f in fam]
        assert all(got) or not any(got)


def test_after_baseline_the_next_family_becomes_focus(kid):
    kid.practice()
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.kind == "normal"
    assert plan.focus_family == "f:2x5"
    assert set(plan.introduced) == set(kid.keys_of("f:2x5"))
    assert set(kid.keys_of("f:2x5")) <= set(plan.fact_keys)
    assert len(plan.fact_keys) == 10 == len(set(plan.fact_keys))
    assert ap.open_focus(kid.uid, kid.db) == "f:2x5"


def test_half_attempted_baseline_family_can_still_be_introduced(kid):
    kid.attempt("m:2x2")                      # an abandoned baseline
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.focus_family == "f:2x2"        # not every direction attempted yet


# ── Practice shape ─────────────────────────────────────────────────────────

def test_four_direction_focus_gives_4_3_3_with_vacancies_filled(kid):
    kid.practice()                              # baseline: 10 seen directions
    plan = ap.plan_practice(kid.uid, kid.db)
    focus = set(kid.keys_of("f:2x5"))
    assert focus <= set(plan.fact_keys)
    # nothing is eligible yet (one attempt each) and nothing is secure:
    # the other six places are filled from seen directions, stalest first
    others = [k for k in plan.fact_keys if k not in focus]
    assert len(others) == 6 and all(k in ap.load_history(kid.uid, kid.db) for k in others)


def build_history_for_shape(kid):
    """Child with families 2x2..2x4 seen (baseline) and enough history for
    weak and stale pools: 3 weak (5 attempts, 3 wrong), 4 stale (secure)."""
    base = [k for f in ("f:2x2", "f:2x3", "f:2x4") for k in kid.keys_of(f)]
    weak, stale = base[:5], base[5:]
    for k in weak:
        for c in (1, 0, 0, 1, 0):
            kid.attempt(k, c)
    kid.secure(stale)
    return base, weak, stale


def test_slots_four_direction_family(kid):
    base, weak, stale = build_history_for_shape(kid)
    plan = ap.plan_practice(kid.uid, kid.db)
    focus = set(kid.keys_of("f:2x5"))
    got = plan.fact_keys
    assert len(got) == 10 and set(got) & focus == focus
    assert len([k for k in got if k in weak]) == 3          # 3 weak of the 5 eligible
    assert len([k for k in got if k in stale]) == 3         # 3 of the 5 stale
    # weak first picks lowest accuracy then least recent
    pools = ap.build_pools(ap.load_history(kid.uid, kid.db), exclude=focus)
    assert [k for k in got if k in weak] == pools.weak[:3]


def test_slots_square_family_2_4_4(kid):
    # Make a square family the next to introduce: mark every earlier rung 1
    # family as introduced with a closed focus row.
    rung1 = families_up_to_rung(1)
    square = "f:10x10"
    for fam in rung1:
        if fam == square:
            break
        kid.db.execute(
            "INSERT INTO arithmetic_focus (user_id,family_key,started_at,completed_at) "
            "VALUES (?,?,'t','t')", (kid.uid, fam))
    ap.ensure_first_rung(kid.uid, kid.db)
    seen = kid.keys_of("f:2x2") + kid.keys_of("f:2x3") + kid.keys_of("f:2x4")
    weak = seen[:6]
    for k in weak:
        for c in (1, 0, 0, 1, 0):
            kid.attempt(k, c)
    kid.secure(seen[6:])
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.focus_family == square and len(FAMILIES[square]) == 2
    assert len(plan.fact_keys) == 10
    assert len([k for k in plan.fact_keys if k in weak]) == 4
    assert len([k for k in plan.fact_keys if k in seen[6:]]) == 4
    assert set(kid.keys_of(square)) <= set(plan.fact_keys)


def test_nothing_to_introduce_gives_six_weak_four_stale(kid):
    # Every available family is introduced but rung 1 is not complete.
    for fam in families_up_to_rung(1):
        kid.db.execute(
            "INSERT INTO arithmetic_focus (user_id,family_key,started_at,completed_at) "
            "VALUES (?,?,'t','t')", (kid.uid, fam))
    ap.ensure_first_rung(kid.uid, kid.db)
    keys = [x.key for f in families_up_to_rung(1) for x in FAMILIES[f]]
    weak, stale = keys[:8], keys[8:14]
    for k in weak:
        for c in (0, 0, 1, 0, 0):
            kid.attempt(k, c)
    kid.secure(stale)
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.focus_family is None and plan.kind == "normal"
    assert len(plan.fact_keys) == 10
    assert len([k for k in plan.fact_keys if k in weak]) == 6
    assert len([k for k in plan.fact_keys if k in stale]) == 4
    assert ap.latest_rung(kid.uid, kid.db) == 1       # still not complete


def test_no_direction_twice_and_no_unseen_filler(kid):
    kid.practice()
    for _ in range(6):
        plan = kid.practice(lambda k: 0 if hash(k) % 3 == 0 else 1)
        assert len(plan.fact_keys) == len(set(plan.fact_keys))
        hist = ap.load_history(kid.uid, kid.db)
        # every question is either in the focus family or already seen
        assert all(k in hist for k in plan.fact_keys)


# ── Focus family ───────────────────────────────────────────────────────────

def test_direction_leaves_focus_after_three_correct_in_a_row(kid):
    kid.practice()
    ap.plan_practice(kid.uid, kid.db)             # opens f:2x5
    fam = kid.keys_of("f:2x5")
    for correct in (1, 1, 1):
        kid.attempt(fam[0], correct)
    for correct in (1, 0, 1, 1):
        kid.attempt(fam[1], correct)
    hist = ap.load_history(kid.uid, kid.db)
    assert ap.focus_remaining(kid.uid, "f:2x5", kid.db, hist) == fam[1:]


def test_freed_focus_slots_go_to_weak(kid):
    base, weak, stale = build_history_for_shape(kid)
    ap.plan_practice(kid.uid, kid.db)             # opens f:2x5
    fam = kid.keys_of("f:2x5")
    for k in fam[:2]:
        kid.secure([k])
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.focus_family == "f:2x5"
    assert len([k for k in plan.fact_keys if k in fam[2:]]) == 2   # two still in focus
    assert len(plan.fact_keys) == 10
    # weak slots: 3 + 2 freed = 5, filled from the five eligible weak
    assert len([k for k in plan.fact_keys if k in weak]) == 5


def test_family_stays_focus_until_all_directions_leave_then_next_family(kid):
    kid.practice()
    ap.plan_practice(kid.uid, kid.db)
    fam = kid.keys_of("f:2x5")
    kid.secure(fam[:3])
    assert ap.plan_practice(kid.uid, kid.db).focus_family == "f:2x5"
    kid.secure(fam[3:])
    plan = ap.plan_practice(kid.uid, kid.db)
    assert plan.focus_family == "f:2x6"           # next family, next practice
    rows = kid.db.execute(
        "SELECT family_key, completed_at FROM arithmetic_focus ORDER BY started_at, family_key").fetchall()
    assert {r["family_key"]: r["completed_at"] is not None for r in rows} == {
        "f:2x5": True, "f:2x6": False}


def test_second_and_topup_attempts_are_not_evidence(kid):
    kid.practice()
    fam = kid.keys_of("f:2x5")
    for _ in range(3):
        kid.attempt(fam[0], 1, number=2)
        kid.attempt(fam[0], 1, number=3)
    assert fam[0] not in ap.load_history(kid.uid, kid.db)
    assert kid.db.execute("SELECT COUNT(*) FROM arithmetic_focus").fetchone()[0] == 0


def test_secure_needs_latest_three_correct_and_demotion_is_immediate():
    assert ap.is_secure([(1, 1), (2, 1), (3, 1)])
    assert not ap.is_secure([(1, 1), (2, 1)])
    assert not ap.is_secure([(1, 1), (2, 1), (3, 1), (4, 0)])
    assert ap.is_secure([(1, 0), (2, 1), (3, 1), (4, 1)])


def test_weak_needs_five_attempts_and_is_ranked_by_recent_accuracy_then_staleness():
    h = {
        "m:2x3": [(1, 0), (2, 0), (3, 1), (4, 0), (5, 0)],     # 1/5
        "m:3x2": [(6, 1), (7, 0), (8, 1), (9, 0), (10, 0)],     # 2/5
        "d:6/2": [(11, 0), (12, 0), (13, 0), (14, 0)],          # only 4 attempts: not eligible
        "d:6/3": [(15, 0), (16, 0), (17, 1), (18, 0), (19, 0)], # 1/5, more recent than m:2x3
    }
    pools = ap.build_pools(h)
    assert pools.weak == ["m:2x3", "d:6/3", "m:3x2"]
    assert pools.other_seen == ["d:6/2"]


def test_stale_is_secure_longest_since_practice_first():
    h = {
        "m:2x3": [(5, 1), (6, 1), (7, 1)],
        "m:3x2": [(1, 1), (2, 1), (3, 1)],
        "d:6/2": [(8, 1), (9, 1), (10, 1)],
    }
    assert ap.build_pools(h).stale == ["m:3x2", "m:2x3", "d:6/2"]


# ── Rungs ──────────────────────────────────────────────────────────────────

def test_rung_two_opens_only_when_every_rung_one_direction_is_secure(kid):
    ap.ensure_first_rung(kid.uid, kid.db)
    keys = facts_of_rung(1)
    kid.secure(keys[:-1])
    hist = ap.load_history(kid.uid, kid.db)
    assert ap.unlock_rungs(kid.uid, kid.db, hist) == []
    assert ap.latest_rung(kid.uid, kid.db) == 1
    kid.secure(keys[-1:])
    hist = ap.load_history(kid.uid, kid.db)
    assert ap.unlock_rungs(kid.uid, kid.db, hist) == [2]
    assert ap.latest_rung(kid.uid, kid.db) == 2
    assert "f:3x5" in ap.available_families(kid.uid, kid.db)
    assert "f:3x4" not in ap.available_families(kid.uid, kid.db)


def test_demotion_blocks_unlock_but_never_relocks(kid):
    ap.ensure_first_rung(kid.uid, kid.db)
    keys = facts_of_rung(1)
    kid.secure(keys)
    kid.attempt(keys[0], 0)                   # slips after being secure
    hist = ap.load_history(kid.uid, kid.db)
    assert ap.unlock_rungs(kid.uid, kid.db, hist) == []
    assert ap.latest_rung(kid.uid, kid.db) == 1
    kid.secure([keys[0]])
    ap.unlock_rungs(kid.uid, kid.db, ap.load_history(kid.uid, kid.db))
    assert ap.latest_rung(kid.uid, kid.db) == 2
    kid.attempt(keys[1], 0)                   # later slip: rung 2 stays open
    ap.unlock_rungs(kid.uid, kid.db, ap.load_history(kid.uid, kid.db))
    assert ap.unlocked_rungs(kid.uid, kid.db) == [1, 2]


def test_plan_unlocks_next_rung_and_introduces_its_first_family(kid):
    ap.ensure_first_rung(kid.uid, kid.db)
    kid.secure(facts_of_rung(1))
    for fam in families_up_to_rung(1):
        kid.db.execute(
            "INSERT INTO arithmetic_focus (user_id,family_key,started_at,completed_at) "
            "VALUES (?,?,'t','t')", (kid.uid, fam))
    plan = ap.plan_practice(kid.uid, kid.db)
    assert ap.latest_rung(kid.uid, kid.db) == 2
    assert plan.focus_family == "f:3x5"
    assert len(plan.fact_keys) == 10


def test_started_rungs_reports_rung_of_first_attempted_direction(kid):
    kid.attempt("m:2x3")
    kid.attempt("m:3x5")
    kid.attempt("m:3x5")
    assert [r for r, _ in ap.started_rungs(kid.uid, kid.db)] == [1, 2]


def test_topup_candidates_exclude_used_and_never_include_unseen(kid):
    kid.practice()
    used = set(ap.plan_practice(kid.uid, kid.db).fact_keys)
    cands = ap.topup_candidates(kid.uid, kid.db, used)
    hist = ap.load_history(kid.uid, kid.db)
    assert not (set(cands) & used)
    assert all(c in hist for c in cands)

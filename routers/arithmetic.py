"""Times-tables practice. The flow mirrors routers/spelling.py:
start, ten questions (a clue and one more try after a wrong first answer),
optional one-at-a-time top-ups, then results and rewards."""
import random
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from auth import require_child
from database import get_db
from services import arithmetic_progression as progression
from services.arithmetic_facts import (
    division_clue_svg, division_clue_text, get_fact, multiplication_clue_lines,
)
from services.game_rewards import badges_until_next, check_and_unlock, next_locked, unlocked_files
from services.gamification import (
    award_arithmetic_trophies, award_session_badge, record_arithmetic_mastery_and_medals,
)
from templates_env import CLASSIC_GAMES, REWARD_GAMES, templates

router = APIRouter(prefix="/arithmetic")

QUESTIONS_PER_PRACTICE = 10
BONUS_TARGET = 20
MAX_RESPONSE_MS = 10 * 60 * 1000      # a client time above this is not believed
CLIENT_TIME_SLACK_MS = 2000           # allowed excess of client time over server time
SESSION_KEY = "arith"
ANSWER_RE = re.compile(r"^\d{1,6}$")


def response_ms_for(raw: str | None, shown_at: float | None) -> int | None:
    """Time from question display to answer. The browser measures it and
    sends it in a hidden field. The server clamps it to a sane range, never
    lets it exceed its own clock by more than a small slack, and falls back
    to its own clock when the field is missing or not a number."""
    server_ms = None
    if shown_at is not None:
        server_ms = max(0, min(int((time.time() - shown_at) * 1000), MAX_RESPONSE_MS))
    raw = (raw or "").strip()
    if ANSWER_RE.match(raw):
        value = min(int(raw), MAX_RESPONSE_MS)
        if server_ms is not None:
            value = min(value, server_ms + CLIENT_TIME_SLACK_MS)
        return value
    return server_ms


@router.get("/start")
def start_practice(request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        plan = progression.plan_practice(user_id, db, QUESTIONS_PER_PRACTICE)
        keys = list(plan.fact_keys)
        if not keys:
            return RedirectResponse("/child/dashboard", status_code=303)
        # Presentation order only; which questions appear is decided above
        random.shuffle(keys)
        now = datetime.now(timezone.utc).isoformat()
        cur = db.execute(
            """INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score, subject)
               VALUES (?,?,NULL,0,?,'arithmetic')""",
            (now, user_id, QUESTIONS_PER_PRACTICE * 2),
        )
        session_id = cur.lastrowid

    request.session[SESSION_KEY] = {
        "session_id": session_id,
        "queue": keys,
        "current_index": 0,
        "attempt_number": 1,
    }
    return RedirectResponse("/arithmetic/question", status_code=303)


def _clue_context(fact, attempt: int, bonus: bool) -> dict:
    """The method clue, shown only on the second attempt of an ordinary
    question. It never contains the answer."""
    if bonus or attempt != 2:
        return {"clue_lines": None, "clue_text": None, "clue_svg": None}
    if fact.kind == "m":
        return {
            "clue_lines": multiplication_clue_lines(fact),
            "clue_text": f"Let's count in {fact.right}s.",
            "clue_svg": None,
        }
    return {"clue_lines": None, "clue_text": division_clue_text(fact),
            "clue_svg": division_clue_svg(fact)}


@router.get("/question")
def show_question(request: Request, user=Depends(require_child)):
    test = request.session.get(SESSION_KEY)
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)

    if request.query_params.get("continue") == "1":
        test.pop("reveal", None)
    elif test.get("reveal"):
        return RedirectResponse("/arithmetic/feedback", status_code=303)

    idx = test["current_index"]
    queue = test["queue"]
    bonus = "bonus_key" in test
    if not bonus and idx >= len(queue):
        request.session[SESSION_KEY] = test
        return RedirectResponse("/arithmetic/topup", status_code=303)

    key = test["bonus_key"] if bonus else queue[idx]
    attempt = 1 if bonus else test["attempt_number"]
    fact = get_fact(key)
    with get_db() as db:
        is_new = (not bonus) and progression.is_introduction(
            user["user_id"], key, test["session_id"], db
        )

    test["shown_at"] = time.time()
    request.session[SESSION_KEY] = test
    ctx = {
        "fact_key": key,
        "question": fact.text,
        "attempt": attempt,
        "question_number": idx + 1,
        "total_questions": len(queue),
        "completed_questions": min(idx, len(queue)),
        "well_done": request.query_params.get("well_done") == "1",
        "bonus": bonus,
        "is_new": is_new,
    }
    ctx.update(_clue_context(fact, attempt, bonus))
    return templates.TemplateResponse(request, "child/arithmetic_question.html", ctx)


@router.post("/question")
def submit_answer(
    request: Request,
    fact_key: str = Form(...),
    answer: str = Form(...),
    response_ms: str = Form(""),
    user=Depends(require_child),
):
    test = request.session.get(SESSION_KEY)
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)
    if test.get("reveal"):
        return RedirectResponse("/arithmetic/feedback", status_code=303)

    bonus = "bonus_key" in test
    if bonus:
        expected = test["bonus_key"]
    else:
        idx = test["current_index"]
        if idx >= len(test["queue"]):
            return RedirectResponse("/arithmetic/topup", status_code=303)
        expected = test["queue"][idx]
    # Only accept an answer for the question currently being asked
    if fact_key != expected:
        return RedirectResponse("/arithmetic/question", status_code=303)
    answer = answer.strip()
    if not ANSWER_RE.match(answer):
        # Not a number: ask again without using up an attempt
        return RedirectResponse("/arithmetic/question", status_code=303)

    fact = get_fact(expected)
    attempt = 3 if bonus else test["attempt_number"]
    correct = int(int(answer) == fact.answer)
    ms = response_ms_for(response_ms, test.get("shown_at"))
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute(
            """INSERT INTO arithmetic_attempts
               (timestamp, user_id, fact_key, correct, attempt_number, session_id, response_ms)
               VALUES (?,?,?,?,?,?,?)""",
            (now, user["user_id"], expected, correct, attempt, test["session_id"], ms),
        )
        if correct:
            if bonus:
                db.execute(
                    "UPDATE test_sessions SET score=score+1 WHERE id=? AND score<?",
                    (test["session_id"], BONUS_TARGET),
                )
            else:
                db.execute(
                    "UPDATE test_sessions SET score=score+? WHERE id=?",
                    (2 if attempt == 1 else 1, test["session_id"]),
                )

    if bonus:
        test.setdefault("topup_asked", []).append(expected)
        del test["bonus_key"]
        request.session[SESSION_KEY] = test
        return RedirectResponse(
            f"/arithmetic/topup?result={'earned' if correct else 'missed'}", status_code=303
        )

    if correct:
        test["current_index"] += 1
        test["attempt_number"] = 1
        redirect = "/arithmetic/question?well_done=1"
    elif attempt == 1:
        test["attempt_number"] = 2          # the clue and one more try
        redirect = "/arithmetic/question"
    else:
        # Wrong again: show the completed fact kindly, then move on
        test["current_index"] += 1
        test["attempt_number"] = 1
        test["reveal"] = expected
        redirect = "/arithmetic/feedback"
    request.session[SESSION_KEY] = test
    return RedirectResponse(redirect, status_code=303)


@router.get("/feedback")
def feedback(request: Request, user=Depends(require_child)):
    test = request.session.get(SESSION_KEY)
    if not test or not test.get("reveal"):
        return RedirectResponse("/arithmetic/question", status_code=303)
    fact = get_fact(test["reveal"])
    return templates.TemplateResponse(request, "child/arithmetic_feedback.html", {
        "completed_fact": f"{fact.text} = {fact.answer}",
    })


def _next_bonus_fact(user_id: int, test: dict, db) -> str | None:
    """Next question to offer as a top-up: directions missed on the first
    try in this practice first (in the order asked), then the weak-then-stale
    order, excluding everything already used in this practice or a prior
    top-up. Never a new fact. None when both are exhausted."""
    asked = set(test.get("topup_asked", []))
    missed = db.execute(
        """SELECT fact_key FROM arithmetic_attempts
           WHERE session_id=? AND attempt_number=1 AND correct=0 ORDER BY id""",
        (test["session_id"],),
    ).fetchall()
    for row in missed:
        if row["fact_key"] not in asked:
            return row["fact_key"]
    return progression.next_topup_fact(user_id, db, exclude=asked | set(test["queue"]))


def _topup_blocked(test: dict) -> bool:
    return test["current_index"] < len(test["queue"]) or "bonus_key" in test


@router.get("/topup")
def topup_offer(request: Request, user=Depends(require_child)):
    test = request.session.get(SESSION_KEY)
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)
    if _topup_blocked(test):
        return RedirectResponse("/arithmetic/question", status_code=303)

    with get_db() as db:
        session = db.execute(
            "SELECT score, max_score FROM test_sessions WHERE id=?", (test["session_id"],)
        ).fetchone()
        has_more = _next_bonus_fact(user["user_id"], test, db) is not None
    if session["score"] >= BONUS_TARGET or not has_more:
        return RedirectResponse("/arithmetic/results", status_code=303)

    result = request.query_params.get("result")
    return templates.TemplateResponse(request, "child/topup.html", {
        "score": session["score"],
        "max_score": session["max_score"],
        "earned": result == "earned",
        "missed": result == "missed",
        "topup_url": "/arithmetic/topup",
        "results_url": "/arithmetic/results",
        "prompt": "Answer another question to earn an extra point?",
        "button": "Answer another question",
    })


@router.post("/topup")
def topup_accept(request: Request, user=Depends(require_child)):
    test = request.session.get(SESSION_KEY)
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)
    if _topup_blocked(test):
        return RedirectResponse("/arithmetic/question", status_code=303)

    with get_db() as db:
        session = db.execute(
            "SELECT score FROM test_sessions WHERE id=?", (test["session_id"],)
        ).fetchone()
        if session["score"] >= BONUS_TARGET:
            return RedirectResponse("/arithmetic/results", status_code=303)
        key = _next_bonus_fact(user["user_id"], test, db)
    if key is None:
        return RedirectResponse("/arithmetic/results", status_code=303)

    test["bonus_key"] = key
    request.session[SESSION_KEY] = test
    return RedirectResponse("/arithmetic/question", status_code=303)


@router.get("/results")
def results(request: Request, user=Depends(require_child)):
    test = request.session.get(SESSION_KEY)
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)

    session_id = test["session_id"]
    user_id = user["user_id"]
    with get_db() as db:
        session = db.execute("SELECT * FROM test_sessions WHERE id=?", (session_id,)).fetchone()
        rows = db.execute(
            "SELECT * FROM arithmetic_attempts WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
        # The results table lists the question, never its answer
        attempts = [
            {"word": get_fact(r["fact_key"]).text, "attempt_number": r["attempt_number"],
             "correct": r["correct"]}
            for r in rows
        ]

        progression.refresh_focus(user_id, db)
        gamification = {"badge_awarded": False, "medals": [], "trophies": []}
        gamification["badge_awarded"] = award_session_badge(
            user_id, session_id, session["score"], db
        )
        gamification["medals"] = record_arithmetic_mastery_and_medals(user_id, db)
        gamification["trophies"] = award_arithmetic_trophies(user_id, db)
        new_game = check_and_unlock(user_id, gamification, db)

        qualifies = session["score"] >= 10
        games = []
        mystery = None
        if qualifies:
            reward_unlocked = [g for g in REWARD_GAMES if g["file"] in unlocked_files(user_id, db)]
            games = CLASSIC_GAMES + reward_unlocked
            if next_locked(user_id, db):
                mystery = {"hint": badges_until_next(user_id, db)}

    request.session.pop(SESSION_KEY, None)
    if qualifies:
        request.session["game_credit"] = {"score": session["score"]}
    else:
        request.session.pop("game_credit", None)

    return templates.TemplateResponse(request, "child/results.html", {
        "session": session,
        "attempts": attempts,
        "gamification": gamification,
        "games": games,
        "new_game": new_game,
        "mystery": mystery,
        "subject_label": "Times tables practice",
        "item_header": "Question",
        "medal_noun": "facts",
        "again_url": "/arithmetic/start",
    })


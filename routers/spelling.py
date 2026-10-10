from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
import random
from datetime import datetime, timezone

from database import get_db
from auth import require_child, generate_csrf_token
from services import spelling_progression as progression
from services.gamification import (
    award_session_badge, award_start_trophies, record_mastery_and_medals,
)
from services.game_rewards import check_and_unlock
from services.game_activity import offer_games
from services.tts import get_audio_url, get_sentence_audio_url
from templates_env import templates

router = APIRouter(prefix="/test")

WORDS_PER_TEST = 10
# A finished test can be topped up +1 point per extra word until this score
BONUS_TARGET = 20


@router.get("/start")
def start_test(request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        plan = progression.plan_practice(user_id, db, WORDS_PER_TEST)
        if not plan.word_ids:
            return RedirectResponse("/child/dashboard", status_code=303)
        word_ids = list(plan.word_ids)
        # Presentation order only; which words appear is decided above
        random.shuffle(word_ids)

        word_rows = [
            db.execute("SELECT word, context_sentence FROM words WHERE id=?", (wid,)).fetchone()
            for wid in word_ids
        ]

    # Pre-generate audio outside the main transaction so that gTTS calls
    # (which can be slow) don't hold the DB write lock.  Rapid successive
    # calls mid-test can trigger Google's soft rate-limit, returning
    # near-silent audio instead of raising an error.
    for row in word_rows:
        with get_db() as db:
            get_audio_url(row["word"], db)
            if row["context_sentence"]:
                get_sentence_audio_url(row["word"], row["context_sentence"], db)

    with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        cur = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES (?,?,NULL,0,?)",
            (now, user_id, WORDS_PER_TEST * 2),
        )
        session_id = cur.lastrowid

    request.session["test"] = {
        "session_id": session_id,
        "word_queue": word_ids,
        "current_index": 0,
        "attempt_number": 1,
    }
    return RedirectResponse("/test/word", status_code=303)


@router.get("/word")
def show_word(request: Request, user=Depends(require_child)):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)

    idx = test["current_index"]
    word_queue = test["word_queue"]
    bonus = "bonus_word_id" in test

    if not bonus and idx >= len(word_queue):
        return RedirectResponse("/test/topup", status_code=303)

    word_id = test["bonus_word_id"] if bonus else word_queue[idx]
    # Bonus words are always presented like attempt 1: audio only, one try
    attempt = 1 if bonus else test["attempt_number"]
    well_done = request.query_params.get("well_done") == "1"

    with get_db() as db:
        word_row = db.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
        if not word_row:
            raise HTTPException(500, "Word not found")

        # Attempt 1: audio only — word must NOT appear in page source
        # Attempt 2: word shown visually so child can study it before second try
        # Attempt 2 also gets the (hashed, so spelling-free) audio URL, for
        # the "Hear the word again" button shown after the word is hidden.
        audio_url = get_audio_url(word_row["word"], db)
        word_text = word_row["word"] if attempt == 2 else None
        is_new = (not bonus) and progression.is_introduction(
            user["user_id"], word_id, test["session_id"], db
        )
        phrase_audio_url = get_audio_url("not quite, try again", db) if attempt == 2 else None
        sentence_audio_url = None
        if attempt == 1 and word_row["context_sentence"]:
            sentence_audio_url = get_sentence_audio_url(
                word_row["word"], word_row["context_sentence"], db
            )

    return templates.TemplateResponse(request, "child/test.html", {
        "word_id": word_id,
        "word_text": word_text,
        "audio_url": audio_url,
        "attempt": attempt,
        "word_number": idx + 1,
        "total_words": len(word_queue),
        "completed_words": min(idx, len(word_queue)),
        "well_done": well_done,
        "phrase_audio_url": phrase_audio_url,
        "sentence_audio_url": sentence_audio_url,
        "bonus": bonus,
        "is_new": is_new,
    })


@router.post("/word")
def submit_word(
    request: Request,
    word_id: int = Form(...),
    answer: str = Form(...),
    user=Depends(require_child),
):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)

    if "bonus_word_id" in test:
        return _submit_bonus_word(request, test, word_id, answer, user)

    idx = test["current_index"]
    word_queue = test["word_queue"]
    if idx >= len(word_queue):
        return RedirectResponse("/test/topup", status_code=303)
    # Only accept an answer for the word currently being asked — rejects
    # stale forms, double submissions, and hand-crafted word_ids
    if word_id != word_queue[idx]:
        return RedirectResponse("/test/word", status_code=303)

    user_id = user["user_id"]
    attempt = test["attempt_number"]
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        word_row = db.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
        if not word_row:
            raise HTTPException(500)

        correct = int(answer.strip().lower() == word_row["word"].strip().lower())
        db.execute(
            """INSERT INTO spelling_attempts
               (timestamp, user_id, word_id, correct, attempt_number, session_id)
               VALUES (?,?,?,?,?,?)""",
            (now, user_id, word_id, correct, attempt, test["session_id"]),
        )

        # Score: 2 for correct on attempt 1, 1 for correct on attempt 2
        if correct:
            points = 2 if attempt == 1 else 1
            db.execute(
                "UPDATE test_sessions SET score=score+? WHERE id=?",
                (points, test["session_id"]),
            )

    if correct or attempt == 2:
        test["current_index"] += 1
        test["attempt_number"] = 1
    else:
        # Wrong on attempt 1 — give attempt 2
        test["attempt_number"] = 2

    request.session["test"] = test
    redirect_url = "/test/word?well_done=1" if correct else "/test/word"
    return RedirectResponse(redirect_url, status_code=303)


def _submit_bonus_word(request: Request, test: dict, word_id: int, answer: str, user):
    """Handle an answer to a top-up bonus word: one attempt, +1 point if
    correct, recorded as attempt 3 so first/second-try mastery is untouched."""
    if word_id != test["bonus_word_id"]:
        return RedirectResponse("/test/word", status_code=303)

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        word_row = db.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
        if not word_row:
            raise HTTPException(500)

        correct = int(answer.strip().lower() == word_row["word"].strip().lower())
        db.execute(
            """INSERT INTO spelling_attempts
               (timestamp, user_id, word_id, correct, attempt_number, session_id)
               VALUES (?,?,?,?,3,?)""",
            (now, user["user_id"], word_id, correct, test["session_id"]),
        )
        if correct:
            db.execute(
                "UPDATE test_sessions SET score=score+1 WHERE id=? AND score<?",
                (test["session_id"], BONUS_TARGET),
            )

    test.setdefault("topup_asked", []).append(word_id)
    del test["bonus_word_id"]
    request.session["test"] = test
    result = "earned" if correct else "missed"
    return RedirectResponse(f"/test/topup?result={result}", status_code=303)


def _next_bonus_word(user_id: int, test: dict, db) -> int | None:
    """Next word to offer as a top-up: words missed on attempt 1 this
    session first (in the order they were asked), then the weak-then-stale
    order, excluding every word already used in this practice or a prior
    top-up; None when both are exhausted."""
    asked = set(test.get("topup_asked", []))
    missed_rows = db.execute(
        """SELECT word_id FROM spelling_attempts
           WHERE session_id=? AND attempt_number=1 AND correct=0 ORDER BY id""",
        (test["session_id"],),
    ).fetchall()
    for row in missed_rows:
        if row["word_id"] not in asked:
            return row["word_id"]

    return progression.next_topup_word(
        user_id, db, exclude=asked | set(test["word_queue"])
    )


@router.get("/topup")
def topup_offer(request: Request, user=Depends(require_child)):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)
    if test["current_index"] < len(test["word_queue"]) or "bonus_word_id" in test:
        return RedirectResponse("/test/word", status_code=303)

    with get_db() as db:
        session = db.execute(
            "SELECT score, max_score FROM test_sessions WHERE id=?",
            (test["session_id"],),
        ).fetchone()
        has_more = _next_bonus_word(user["user_id"], test, db) is not None

    if session["score"] >= BONUS_TARGET or not has_more:
        return RedirectResponse("/test/results", status_code=303)

    result = request.query_params.get("result")
    return templates.TemplateResponse(request, "child/topup.html", {
        "score": session["score"],
        "max_score": session["max_score"],
        "earned": result == "earned",
        "missed": result == "missed",
    })


@router.post("/topup")
def topup_accept(request: Request, user=Depends(require_child)):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)
    if test["current_index"] < len(test["word_queue"]) or "bonus_word_id" in test:
        return RedirectResponse("/test/word", status_code=303)

    with get_db() as db:
        session = db.execute(
            "SELECT score FROM test_sessions WHERE id=?", (test["session_id"],)
        ).fetchone()
        if session["score"] >= BONUS_TARGET:
            return RedirectResponse("/test/results", status_code=303)
        wid = _next_bonus_word(user["user_id"], test, db)

    if wid is None:
        return RedirectResponse("/test/results", status_code=303)

    test["bonus_word_id"] = wid
    request.session["test"] = test
    return RedirectResponse("/test/word", status_code=303)


@router.get("/results")
def results(request: Request, user=Depends(require_child)):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)

    session_id = test["session_id"]
    user_id = user["user_id"]

    with get_db() as db:
        session = db.execute("SELECT * FROM test_sessions WHERE id=?", (session_id,)).fetchone()
        attempts = db.execute(
            """SELECT sa.*, w.word
               FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
               WHERE sa.session_id=? ORDER BY sa.id""",
            (session_id,),
        ).fetchall()

        # Close the focus word if this practice completed it, then award.
        progression.refresh_focus(user_id, db)
        gamification = {"badge_awarded": False, "medals": [], "trophies": []}
        gamification["badge_awarded"] = award_session_badge(
            user_id, session_id, session["score"], db
        )
        gamification["medals"] = record_mastery_and_medals(user_id, db)
        gamification["trophies"] = award_start_trophies(user_id, db)

        # Only every third badge unlocks a game (medals and trophies do not)
        new_game = check_and_unlock(user_id, gamification, db)

        games = offer_games(user_id, session_id, session["score"], db)

    # Clear test session state
    request.session.pop("test", None)

    # Credit state lives server-side, so replaying an older signed session
    # cookie cannot mint or spend another game play.
    request.session.pop("game_credit", None)

    return templates.TemplateResponse(request, "child/results.html", {
        "session": session,
        "attempts": attempts,
        "csrf_token": generate_csrf_token(request),
        "gamification": gamification,
        "new_game": new_game,
        **games,
    })

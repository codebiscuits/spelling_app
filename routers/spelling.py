from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone
import random

from database import get_db
from auth import require_child
from services.word_selection import select_words
from services.gamification import check_and_award
from services.tts import get_audio_url
from templates_env import templates, MINI_GAMES

router = APIRouter(prefix="/test")

WORDS_PER_TEST = 10


@router.get("/start/{list_id}")
def start_test(list_id: int, request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        # Verify child has this list unlocked
        unlock = db.execute(
            "SELECT 1 FROM user_list_unlocks WHERE user_id=? AND list_id=?",
            (user_id, list_id),
        ).fetchone()
        if not unlock:
            raise HTTPException(403, "List not unlocked")

        word_ids = select_words(user_id, list_id, WORDS_PER_TEST, db)
        if not word_ids:
            raise HTTPException(400, "No words in list")

        now = datetime.now(timezone.utc).isoformat()
        cur = db.execute(
            "INSERT INTO test_sessions (timestamp, user_id, list_id, score, max_score) VALUES (?,?,?,0,?)",
            (now, user_id, list_id, WORDS_PER_TEST * 2),
        )
        session_id = cur.lastrowid

    request.session["test"] = {
        "session_id": session_id,
        "list_id": list_id,
        "word_queue": word_ids,
        "current_index": 0,
        "attempt_number": 1,
    }
    return RedirectResponse("/test/word", status_code=303)


@router.get("/word")
def show_word(request: Request, user=Depends(require_child)):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/pick-list", status_code=303)

    idx = test["current_index"]
    word_queue = test["word_queue"]

    if idx >= len(word_queue):
        return RedirectResponse("/test/results", status_code=303)

    word_id = word_queue[idx]
    attempt = test["attempt_number"]
    well_done = request.query_params.get("well_done") == "1"

    with get_db() as db:
        word_row = db.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
        if not word_row:
            raise HTTPException(500, "Word not found")

        # Attempt 1: audio only — word must NOT appear in page source
        # Attempt 2: word shown visually so child can study it before second try
        audio_url = get_audio_url(word_row["word"], db) if attempt == 1 else None
        word_text = word_row["word"] if attempt == 2 else None

    return templates.TemplateResponse(request, "child/test.html", {
        "word_id": word_id,
        "word_text": word_text,
        "audio_url": audio_url,
        "attempt": attempt,
        "word_number": idx + 1,
        "total_words": len(word_queue),
        "well_done": well_done,
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
        return RedirectResponse("/child/pick-list", status_code=303)

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


@router.get("/results")
def results(request: Request, user=Depends(require_child)):
    test = request.session.get("test")
    if not test:
        return RedirectResponse("/child/dashboard", status_code=303)

    session_id = test["session_id"]
    list_id = test["list_id"]
    user_id = user["user_id"]

    with get_db() as db:
        session = db.execute("SELECT * FROM test_sessions WHERE id=?", (session_id,)).fetchone()
        attempts = db.execute(
            """SELECT sa.*, w.word
               FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
               WHERE sa.session_id=? ORDER BY sa.id""",
            (session_id,),
        ).fetchall()
        list_row = db.execute("SELECT * FROM word_lists WHERE id=?", (list_id,)).fetchone()
        gamification = check_and_award(user_id, list_id, session_id, session["score"], db)

    # Clear test session state
    request.session.pop("test", None)

    # Mini game reward: unlock when score >= 10/20 (50%)
    # When adjusting this threshold, update README.md and SETUP.md as well
    game_reward = None
    if MINI_GAMES and session["score"] >= 10:
        game_reward = random.choice(MINI_GAMES)

    return templates.TemplateResponse(request, "child/results.html", {
        "session": session,
        "attempts": attempts,
        "list": list_row,
        "gamification": gamification,
        "game_reward": game_reward,
    })

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
    user_mode = user.get("mode", "audio")

    with get_db() as db:
        word_row = db.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
        if not word_row:
            raise HTTPException(500, "Word not found")

        audio_url = None
        if user_mode == "audio" or attempt == 2:
            audio_url = get_audio_url(word_row["word"], db)

    # Audio mode attempt 1: word MUST NOT be in page source.
    # Visual mode attempt 1: word shown briefly via JS (acceptable — it's displayed visually).
    # Attempt 2 (both modes): word shown so child can study it before second try.
    if attempt == 2 or (user_mode == "visual" and attempt == 1):
        word_text = word_row["word"]
    else:
        word_text = None

    return templates.TemplateResponse(request, "child/test.html", {
        "word_id": word_id,
        "word_text": word_text,   # None on attempt 1 — never in source
        "audio_url": audio_url,
        "attempt": attempt,
        "mode": user_mode,
        "word_number": idx + 1,
        "total_words": len(word_queue),
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
        # Move to next word
        test["current_index"] += 1
        test["attempt_number"] = 1
    else:
        # Wrong on attempt 1 — give attempt 2
        test["attempt_number"] = 2

    request.session["test"] = test
    return RedirectResponse("/test/word", status_code=303)


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
        gamification = check_and_award(user_id, list_id, db)

    # Clear test session state
    request.session.pop("test", None)

    # Mini game reward: unlock when score >= 16/20 (80%)
    game_reward = None
    if MINI_GAMES and session["score"] >= 16:
        game_reward = random.choice(MINI_GAMES)

    return templates.TemplateResponse(request, "child/results.html", {
        "session": session,
        "attempts": attempts,
        "list": list_row,
        "gamification": gamification,
        "game_reward": game_reward,
    })

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone

from database import get_db
from auth import require_child
from services.word_selection import select_words
from services.gamification import check_and_award
from services.tts import get_audio_url, get_sentence_audio_url
from templates_env import templates, MINI_GAMES

router = APIRouter(prefix="/test")

WORDS_PER_TEST = 10


@router.get("/start")
def start_test(request: Request, user=Depends(require_child)):
    user_id = user["user_id"]
    with get_db() as db:
        unlock_rows = db.execute(
            "SELECT list_id FROM user_list_unlocks WHERE user_id=?", (user_id,)
        ).fetchall()
        list_ids = [r["list_id"] for r in unlock_rows]
        if not list_ids:
            return RedirectResponse("/child/dashboard", status_code=303)

        word_ids = select_words(user_id, list_ids, WORDS_PER_TEST, db)
        if not word_ids:
            return RedirectResponse("/child/dashboard", status_code=303)

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
        "well_done": well_done,
        "phrase_audio_url": phrase_audio_url,
        "sentence_audio_url": sentence_audio_url,
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

    idx = test["current_index"]
    word_queue = test["word_queue"]
    if idx >= len(word_queue):
        return RedirectResponse("/test/results", status_code=303)
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

        # Determine which lists had words in this session, then run gamification for each
        distinct_list_ids = db.execute(
            """SELECT DISTINCT w.list_id
               FROM spelling_attempts sa JOIN words w ON w.id=sa.word_id
               WHERE sa.session_id=?""",
            (session_id,),
        ).fetchall()

        gamification = {"badge_awarded": False, "medal_awarded": False, "trophy_awarded": False, "lists_unlocked": []}
        for row in distinct_list_ids:
            result = check_and_award(user_id, row["list_id"], session_id, session["score"], db)
            gamification["badge_awarded"] = gamification["badge_awarded"] or result["badge_awarded"]
            gamification["medal_awarded"] = gamification["medal_awarded"] or result["medal_awarded"]
            gamification["trophy_awarded"] = gamification["trophy_awarded"] or result["trophy_awarded"]
            gamification["lists_unlocked"].extend(result["lists_unlocked"])

    # Clear test session state
    request.session.pop("test", None)

    # Mini game reward: unlock when score >= 10/20 (50%)
    # When adjusting this threshold, update README.md and SETUP.md as well
    games = MINI_GAMES if (MINI_GAMES and session["score"] >= 10) else []

    return templates.TemplateResponse(request, "child/results.html", {
        "session": session,
        "attempts": attempts,
        "gamification": gamification,
        "games": games,
    })

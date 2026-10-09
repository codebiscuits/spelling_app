"""Admin-only progress monitoring: read-only pages over existing evidence.

Detailed diagnostics stay here. Nothing in this module is child-facing,
and every route needs the admin guard.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_admin
from database import get_db
from services import arithmetic_progression as arith
from services import progress_monitoring as pm
from services import spelling_progression as spell
from services.arithmetic_facts import FACTS, FAMILY_RUNG
from templates_env import templates

router = APIRouter(prefix="/admin")

TITLES = {pm.SPELLING: "Spelling", pm.ARITHMETIC: "Times tables"}


def _child(db, child_id: int):
    child = db.execute("SELECT * FROM users WHERE id=? AND is_admin=0", (child_id,)).fetchone()
    if not child:
        raise HTTPException(404)
    return child


@router.get("/progress")
def progress_overview(request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        children = db.execute("SELECT * FROM users WHERE is_admin=0 ORDER BY name").fetchall()
        rows = [{
            "child": c,
            "spelling": pm.subject_summary(db, c["id"], pm.SPELLING),
            "arithmetic": pm.subject_summary(db, c["id"], pm.ARITHMETIC),
        } for c in children]
    return templates.TemplateResponse(request, "admin/progress_overview.html", {
        "rows": rows, "recent_days": pm.RECENT_DAYS,
    })


def _subject_page(request: Request, child_id: int, subject: str):
    with get_db() as db:
        child = _child(db, child_id)
        history = pm.practice_history(db, child_id, subject)
        if subject == pm.SPELLING:
            items = pm.spelling_item_rows(db, child_id)
            position = None
        else:
            items = pm.arithmetic_item_rows(db, child_id)
            position = pm.arithmetic_position(db, child_id)
    done = pm.completed_practices(history)
    return templates.TemplateResponse(request, "admin/progress_subject.html", {
        "child": child, "subject": subject, "title": TITLES[subject],
        "history": list(reversed(history)),
        "chart": pm.chart_payload(subject, history, child_id),
        "points": len(done),
        "secure": done[-1]["secure"] if done else 0,
        "review": done[-1]["review"] if done else 0,
        "items": items, "position": position,
        "item_url": f"/admin/children/{child_id}/"
                    + ("spelling/words/" if subject == pm.SPELLING else "arithmetic/facts?key="),
    })


@router.get("/children/{child_id}/spelling")
def spelling_progress(child_id: int, request: Request, admin=Depends(require_admin)):
    return _subject_page(request, child_id, pm.SPELLING)


@router.get("/children/{child_id}/arithmetic")
def arithmetic_progress(child_id: int, request: Request, admin=Depends(require_admin)):
    return _subject_page(request, child_id, pm.ARITHMETIC)


def _practice_page(request: Request, child_id: int, subject: str, session_id: int):
    with get_db() as db:
        child = _child(db, child_id)
        evidence = pm.practice_evidence(db, child_id, subject, session_id)
        if evidence is None:
            raise HTTPException(404)
    item_base = f"/admin/children/{child_id}/" + (
        "spelling/words/" if subject == pm.SPELLING else "arithmetic/facts?key=")
    return templates.TemplateResponse(request, "admin/progress_practice.html", {
        "child": child, "subject": subject, "title": TITLES[subject],
        "ev": evidence, "item_url": item_base,
    })


@router.get("/children/{child_id}/spelling/practices/{session_id}")
def spelling_practice(child_id: int, session_id: int, request: Request,
                      admin=Depends(require_admin)):
    return _practice_page(request, child_id, pm.SPELLING, session_id)


@router.get("/children/{child_id}/arithmetic/practices/{session_id}")
def arithmetic_practice(child_id: int, session_id: int, request: Request,
                        admin=Depends(require_admin)):
    return _practice_page(request, child_id, pm.ARITHMETIC, session_id)


def _item_page(request, child, subject, label, status, focus, entries, extra=None):
    latest = list(reversed(entries[-5:]))
    return templates.TemplateResponse(request, "admin/progress_item.html", {
        "child": child, "subject": subject, "title": TITLES[subject],
        "label": label, "status": status, "focus": focus,
        "latest": latest, "total": len(entries),
        "last_date": entries[-1]["timestamp"][:10] if entries else None,
        "extra": extra,
    })


@router.get("/children/{child_id}/spelling/words/{word_id}")
def spelling_item(child_id: int, word_id: int, request: Request, admin=Depends(require_admin)):
    with get_db() as db:
        child = _child(db, child_id)
        word = db.execute(
            """SELECT w.word, wl.name AS list_name, wl.id AS list_id FROM words w
               JOIN word_lists wl ON wl.id=w.list_id WHERE w.id=?""", (word_id,)
        ).fetchone()
        if not word:
            raise HTTPException(404)
        entries = pm.item_history(db, child_id, pm.SPELLING, word_id)
        pairs = [(e["id"], e["correct"]) for e in entries]
        unlocked = word["list_id"] in spell.available_list_ids(child_id, db)
        focus = spell.open_focus(child_id, db) == word_id
    status = pm.status_label(spell.is_mastered(pairs), bool(entries), pm.SPELLING)
    if not entries and not unlocked:
        status = "Locked (its list is not unlocked yet)"
    return _item_page(request, child, pm.SPELLING, word["word"], status, focus, entries,
                      extra=f"List: {word['list_name']}")


@router.get("/children/{child_id}/arithmetic/facts")
def arithmetic_item(child_id: int, key: str, request: Request, admin=Depends(require_admin)):
    fact = FACTS.get(key)
    if fact is None:
        raise HTTPException(404)
    with get_db() as db:
        child = _child(db, child_id)
        entries = pm.item_history(db, child_id, pm.ARITHMETIC, key)
        pairs = [(e["id"], e["correct"]) for e in entries]
        rung = arith.latest_rung(child_id, db)
        focus = key in pm.focus_directions(db, child_id)
    status = pm.status_label(arith.is_secure(pairs), bool(entries), pm.ARITHMETIC)
    fam_rung = FAMILY_RUNG[fact.family]
    if not entries and fam_rung > rung:
        status = f"Locked (rung {fam_rung} is not unlocked yet)"
    for e in entries:
        e["seconds"] = round(e["ms"] / 1000, 2) if e["ms"] is not None else None
    return _item_page(request, child, pm.ARITHMETIC, f"{fact.text} = {fact.answer}",
                      status, focus, entries, extra=pm.family_label(fact.family))

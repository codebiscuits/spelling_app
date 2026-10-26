"""Warn Ross before the children run out of reward games to unlock.

Run once a day on fileserver (see fileserver/ in the machine-setup repo):

    uv run python scripts/games_left_alert.py --db /home/ross/Apps/spelling_app/spelling.db

It opens the database read-only and forecasts each child's run-out date with
services/games_left.py. If any active child is forecast to run out within
7 days, or has run out, it creates ONE Organiser deadline task, with a phone
notification at 9am the next morning, and ONE Work Graph action. It creates
neither if an alert is already open, so it never repeats itself; completing
the Organiser task and the Work Graph action re-arms it.

    --dry-run   print what it would create, and create nothing

Exit status: 0 when it ran (alert or not), 1 when a service could not be reached.
"""
import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.game_rewards import BADGE_STEP  # noqa: E402
from services.games_left import LEAD_DAYS, PACE_WINDOW_DAYS, all_forecasts  # noqa: E402

ORGANISER = "http://100.74.73.105:8888"
WORKGRAPH = "http://100.74.73.105:8891"
# Work Graph job "Spelling app: learning practice and game pipeline".
WORKGRAPH_PARENT = "01M46JFXNE1W353PF2130EYP7D"
ACTOR = "games-left-alert"
TITLE_PREFIX = "Make more reward games"


def _request(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read() or b"null")


def describe(f: dict) -> str:
    if f["games_left"] == 0:
        when = "has run out"
    else:
        when = f"runs out about {f['run_out']:%-d %b}"
    return (f"{f['name']}: {f['games_left']} of {f['games_total']} games left, "
            f"{f['pace_per_week']} badges a week, {when}")


def title_for(first: dict) -> str:
    if first["games_left"] == 0:
        return f"{TITLE_PREFIX}: {first['name']} has run out"
    return f"{TITLE_PREFIX}: {first['name']} runs out about {first['run_out']:%-d %b}"


def organiser_task(first: dict, lines: list[str], now: datetime) -> dict:
    """Deadline at 5pm on the run-out day, never earlier than 5pm tomorrow.
    One notification, timed to fire at 9am the morning after the alert."""
    tomorrow = now.date() + timedelta(days=1)
    day = max(first["run_out"], tomorrow)
    deadline = datetime.combine(day, time(17, 0))
    notify_at = datetime.combine(tomorrow, time(9, 0))
    offset = int((deadline - notify_at).total_seconds() // 60)
    return {
        "type": "deadline",
        "title": title_for(first),
        "importance": 3,
        "estimated_duration": 120,
        "deadline_at": deadline.isoformat(),
        "notification_offsets": [offset],
        "notes": "\n".join([
            "Created by scripts/games_left_alert.py in the spelling_app repo.",
            f"Pace is badges over the last {PACE_WINDOW_DAYS} days. One game unlocks every {BADGE_STEP} badges.",
            *lines,
            "Build new reward games and add them to MINI_GAMES in templates_env.py.",
        ]),
    }


def workgraph_node(first: dict, lines: list[str]) -> dict:
    summary = (f"{'; '.join(lines)}. The games-left alert forecast this from each child's badge "
               f"pace over {PACE_WINDOW_DAYS} days. Build new reward games, test them on staging, "
               f"and merge them to main before the run-out date.")
    return {
        "label": f"Ross: {title_for(first)[0].lower()}{title_for(first)[1:]}",
        "node_type": "action", "parent_id": WORKGRAPH_PARENT, "status": "open",
        "estimated_minutes": 120, "importance": 2, "urgency": 3,
        "short_label": f"Ross: {TITLE_PREFIX.lower()} before {first['name']} runs out",
        "summary": summary, "source_ref": "projects/software-and-coding/browser-mini-games.md",
        "actor": ACTOR,
    }


def open_organiser_alert(organiser: str):
    tasks = _request("GET", f"{organiser}/tasks/all")
    return next((t for t in tasks if t["title"].startswith(TITLE_PREFIX)
                 and t.get("status") == "pending"), None)


def open_workgraph_alert(workgraph: str):
    nodes = _request("GET", f"{workgraph}/v1/nodes/{WORKGRAPH_PARENT}/open-children")["nodes"]
    return next((n for n in nodes if TITLE_PREFIX.lower() in n["label"].lower()), None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="path to spelling.db, opened read-only")
    ap.add_argument("--organiser", default=ORGANISER)
    ap.add_argument("--workgraph", default=WORKGRAPH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    con = sqlite3.connect(f"file:{Path(args.db).resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        forecasts = all_forecasts(con)
    finally:
        con.close()

    for f in forecasts:
        print(("ALERT  " if f["alert"] else "ok     ") + describe(f) if f["active"]
              else f"idle   {f['name']}: no badges in {PACE_WINDOW_DAYS} days, no forecast")
    due = [f for f in forecasts if f["alert"]]
    if not due:
        print(f"No child runs out within {LEAD_DAYS} days. Nothing to send.")
        return 0

    first = due[0]
    lines = [describe(f) for f in forecasts if f["active"]]
    now = datetime.now()
    task = organiser_task(first, lines, now)
    node = workgraph_node(first, lines)
    if args.dry_run:
        print("DRY RUN. Would create this Organiser task:\n" + json.dumps(task, indent=2))
        print("and this Work Graph action:\n" + json.dumps(node, indent=2))
        return 0

    failed = False
    try:
        existing = open_organiser_alert(args.organiser)
        if existing:
            print(f"Organiser alert already open, task {existing['id']}: {existing['title']}")
        else:
            made = _request("POST", f"{args.organiser}/tasks/", task)
            print(f"Created Organiser task {made.get('id')}: {task['title']}")
    except Exception as e:  # report and carry on, so the other alert still goes out
        print(f"ERROR: Organiser at {args.organiser}: {e}", file=sys.stderr)
        failed = True
    try:
        existing = open_workgraph_alert(args.workgraph)
        if existing:
            print(f"Work Graph alert already open, node {existing['id']}: {existing['label']}")
        else:
            made = _request("POST", f"{args.workgraph}/v1/nodes", node)
            print(f"Created Work Graph action {made.get('id')}: {node['label']}")
    except Exception as e:
        print(f"ERROR: Work Graph at {args.workgraph}: {e}", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

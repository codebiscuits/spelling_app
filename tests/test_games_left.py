"""Games-left forecast and the alert that warns Ross before the children run out."""
import sqlite3
from datetime import date, datetime, timedelta

import pytest

from database import SCHEMA
from scripts import games_left_alert as alert
from services.games_left import all_forecasts, child_forecast
from templates_env import REWARD_GAMES
from tests.conftest import make_list, make_session, make_user

TODAY = date(2026, 10, 12)
TOTAL = len(REWARD_GAMES)


def give_badges(db, uid, days_ago):
    """One badge per entry in days_ago, each on its own practice session."""
    lid = make_list(db, f"L{uid}-{len(days_ago)}")
    for d in days_ago:
        sid = make_session(db, uid, lid)
        stamp = datetime.combine(TODAY - timedelta(days=d), datetime.min.time()).isoformat() + "+00:00"
        db.execute("INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)", (uid, sid, stamp))
    db.commit()


def unlock(db, uid, n):
    for g in REWARD_GAMES[:n]:
        db.execute("INSERT INTO user_game_unlocks VALUES (?,?,?,?)", (uid, g["file"], "2026-01-01T00:00:00+00:00", "badge"))
    db.commit()


def user(db, uid):
    return db.execute("SELECT id, name FROM users WHERE id=?", (uid,)).fetchone()


def test_run_out_date_follows_badge_pace(db):
    uid = make_user(db, "Honey")
    unlock(db, uid, TOTAL - 2)
    give_badges(db, uid, [1, 3, 5, 7, 9, 11, 13])        # 7 badges in 28 days = 0.25 a day
    f = child_forecast(user(db, uid), db, TODAY)
    assert f["games_left"] == 2
    # 7 badges: 2 more to the next multiple of 3, then 3 for the last game.
    assert f["badges_needed"] == 5
    assert f["run_out"] == TODAY + timedelta(days=20)
    assert f["pace_per_week"] == 1.8
    assert f["alert"] is False


def test_alerts_inside_the_seven_day_lead(db):
    uid = make_user(db, "Ollie")
    unlock(db, uid, TOTAL - 1)
    give_badges(db, uid, list(range(1, 15)))             # 14 badges in 28 days = 0.5 a day
    f = child_forecast(user(db, uid), db, TODAY)
    assert f["badges_needed"] == 1                       # 14 badges: one more reaches 15
    assert f["run_out"] == TODAY + timedelta(days=2)
    assert f["alert"] is True


def test_a_child_who_has_run_out_alerts(db):
    uid = make_user(db, "Honey")
    unlock(db, uid, TOTAL)
    give_badges(db, uid, [2])
    f = child_forecast(user(db, uid), db, TODAY)
    assert f["games_left"] == 0 and f["run_out"] == TODAY and f["alert"] is True


def test_an_idle_account_never_alerts(db):
    uid = make_user(db, "Test account")
    unlock(db, uid, TOTAL)
    give_badges(db, uid, [40, 60])                       # outside the 28-day window
    f = child_forecast(user(db, uid), db, TODAY)
    assert f["active"] is False and f["alert"] is False


def test_unlocks_of_removed_games_do_not_count(db):
    uid = make_user(db, "Honey")
    db.execute("INSERT INTO user_game_unlocks VALUES (?,?,?,?)", (uid, "retired_game.html", "2026-01-01T00:00:00+00:00", "badge"))
    db.commit()
    assert child_forecast(user(db, uid), db, TODAY)["games_left"] == TOTAL


def test_earliest_run_out_comes_first_and_admins_are_skipped(db):
    a, b = make_user(db, "Honey"), make_user(db, "Ollie")
    db.execute("UPDATE users SET is_admin=1 WHERE id=?", (make_user(db, "Ross"),))
    unlock(db, a, TOTAL - 3)
    give_badges(db, a, [1, 2])
    unlock(db, b, TOTAL)
    give_badges(db, b, [1])
    names = [f["name"] for f in all_forecasts(db, TODAY)]
    assert names == ["Ollie", "Honey"]


# ── The alert script ────────────────────────────────────────────────────────

@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "spelling.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    con.commit()
    yield path, con
    con.close()


class FakeServices:
    def __init__(self, organiser_tasks=(), workgraph_nodes=()):
        self.tasks, self.nodes, self.posts = list(organiser_tasks), list(workgraph_nodes), []

    def __call__(self, method, url, body=None):
        if method == "GET" and url.endswith("/tasks/all"):
            return self.tasks
        if method == "GET" and url.endswith("/open-children"):
            return {"nodes": self.nodes}
        self.posts.append((url, body))
        return {"id": "new"}


def run_ok(db_file, monkeypatch, services, now_badges=True):
    path, con = db_file
    uid = make_user(con, "Honey")
    unlock(con, uid, TOTAL)
    if now_badges:
        stamp = datetime.now().isoformat(timespec="seconds") + "+00:00"
        sid = make_session(con, uid, make_list(con, "X"))
        con.execute("INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)", (uid, sid, stamp))
        con.commit()
    monkeypatch.setattr(alert, "_request", services)
    return alert.main(["--db", str(path)])


def test_alert_creates_one_task_and_one_node(db_file, monkeypatch):
    fake = FakeServices()
    assert run_ok(db_file, monkeypatch, fake) == 0
    urls = [u for u, _ in fake.posts]
    assert urls == [alert.ORGANISER + "/tasks/", alert.WORKGRAPH + "/v1/nodes"]
    task, node = fake.posts[0][1], fake.posts[1][1]
    assert task["type"] == "deadline" and task["title"] == "Make more reward games: Honey has run out"
    assert node["actor"] == "games-left-alert" and node["parent_id"] == alert.WORKGRAPH_PARENT


def test_alert_never_duplicates_an_open_one(db_file, monkeypatch):
    fake = FakeServices(
        organiser_tasks=[{"id": 9, "title": "Make more reward games: Honey has run out", "status": "pending"}],
        workgraph_nodes=[{"id": "N", "label": "Ross: make more reward games: Honey has run out"}],
    )
    assert run_ok(db_file, monkeypatch, fake) == 0
    assert fake.posts == []


def test_no_alert_when_nobody_is_close(db_file, monkeypatch):
    fake = FakeServices()
    assert run_ok(db_file, monkeypatch, fake, now_badges=False) == 0
    assert fake.posts == []


def test_dry_run_creates_nothing_and_the_database_is_untouched(db_file, monkeypatch):
    path, con = db_file
    fake = FakeServices()
    uid = make_user(con, "Honey")
    unlock(con, uid, TOTAL)
    before = path.read_bytes()
    monkeypatch.setattr(alert, "_request", fake)
    assert alert.main(["--db", str(path), "--dry-run"]) == 0
    assert fake.posts == [] and path.read_bytes() == before


def test_a_service_failure_is_reported_and_the_other_still_sends(db_file, monkeypatch):
    fake = FakeServices()

    def flaky(method, url, body=None):
        if "8888" in url:
            raise OSError("connection refused")
        return fake(method, url, body)
    assert run_ok(db_file, monkeypatch, flaky) == 1
    assert [u for u, _ in fake.posts] == [alert.WORKGRAPH + "/v1/nodes"]


def test_notification_fires_at_nine_the_next_morning():
    now = datetime(2026, 10, 12, 21, 30)
    for run_out in (date(2026, 10, 12), date(2026, 10, 16)):
        first = {"name": "Honey", "games_left": 1, "run_out": run_out}
        task = alert.organiser_task(first, ["x"], now)
        deadline = datetime.fromisoformat(task["deadline_at"])
        assert deadline >= datetime(2026, 10, 13, 17, 0)
        assert deadline - timedelta(minutes=task["notification_offsets"][0]) == datetime(2026, 10, 13, 9, 0)


# ── The admin dashboard line ────────────────────────────────────────────────

def test_admin_dashboard_shows_games_left_and_warns(admin_client):
    from tests.conftest import app_db
    with app_db() as con:
        uid = make_user(con, "Honey")
        unlock(con, uid, TOTAL)
        stamp = datetime.now().isoformat(timespec="seconds") + "+00:00"
        sid = make_session(con, uid, make_list(con, "Y"))
        con.execute("INSERT INTO test_badges (user_id, session_id, earned_at) VALUES (?,?,?)", (uid, sid, stamp))
        make_user(con, "Ollie")
    page = admin_client.get("/admin/").text
    assert f"Reward games left: <strong>0 of {TOTAL}</strong>" in page
    assert "has run out" in page and "games-left-alert" in page
    assert f"Reward games left: <strong>{TOTAL} of {TOTAL}</strong>" in page
    assert "no badges in 4 weeks" in page

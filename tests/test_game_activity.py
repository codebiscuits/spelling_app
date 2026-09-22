from datetime import datetime, timedelta, timezone

from services.game_activity import RECENT_PLAY_WINDOW, recently_played_files
from tests.conftest import make_user


def record_play(db, user_id, game_file, played_at):
    db.execute(
        "INSERT INTO user_game_plays (user_id, game_file, played_at) VALUES (?,?,?)",
        (user_id, game_file, played_at.isoformat()),
    )
    db.commit()


def test_recent_games_include_the_30_day_cutoff_and_exclude_other_children(db):
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    child_id = make_user(db, "Alice")
    other_child_id = make_user(db, "Bob")

    record_play(db, child_id, "circles.html", now - RECENT_PLAY_WINDOW)
    record_play(db, child_id, "fireworks.html", now - RECENT_PLAY_WINDOW - timedelta(microseconds=1))
    record_play(db, other_child_id, "gravity-balls.html", now)

    assert recently_played_files(child_id, db, now=now) == {"circles.html"}


def test_recent_games_normalise_a_non_utc_clock_before_comparing_timestamps(db):
    child_id = make_user(db)
    now_utc = datetime(2026, 2, 1, tzinfo=timezone.utc)
    record_play(db, child_id, "circles.html", now_utc - RECENT_PLAY_WINDOW)

    now_in_eet = now_utc.astimezone(timezone(timedelta(hours=2)))

    assert recently_played_files(child_id, db, now=now_in_eet) == {"circles.html"}

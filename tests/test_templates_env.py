import os

from templates_env import (
    PALETTES,
    MINI_GAMES,
    current_palette,
    game_path,
    game_thumb,
    static_version,
)


def test_seven_palettes_with_five_colours_each():
    assert len(PALETTES) == 7
    for palette in PALETTES:
        assert len(palette["colours"]) == 5
        for colour in palette["colours"]:
            assert colour.startswith("#") and len(colour) == 7


def test_current_palette_is_todays():
    assert current_palette() in PALETTES


def test_every_mini_game_file_exists():
    for game in MINI_GAMES:
        path = game_path(game["file"])
        assert path is not None, f"Missing mini-game file: {game['file']}"
        assert os.path.isfile(path)
        assert game["name"]
        assert game["description"]


def test_every_mini_game_has_a_thumbnail():
    # The picker shows a placeholder without one. Make it with
    # scripts/capture_thumbnails.py when adding a game.
    missing = [g["file"] for g in MINI_GAMES if game_thumb(g["file"]) is None]
    assert not missing, f"No thumbnail for {missing}: run scripts/capture_thumbnails.py"


def test_game_thumb_is_a_versioned_static_url():
    url = game_thumb("domino_run.html")
    assert url.startswith("/static/img/game-thumbs/domino_run.png?v=")


def test_game_thumb_returns_none_for_a_game_with_no_png():
    assert game_thumb("no_such_game.html") is None


def test_game_path_returns_none_for_a_file_that_is_not_there():
    assert game_path("no_such_game.html") is None


def test_static_version_returns_mtime_for_existing_file():
    version = static_version("js/spelling.js")
    assert version == str(int(os.path.getmtime("static/js/spelling.js")))


def test_static_version_returns_zero_for_missing_file():
    assert static_version("js/does_not_exist.js") == "0"

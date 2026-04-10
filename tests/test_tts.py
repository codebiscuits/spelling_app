import os
import pytest
from unittest.mock import MagicMock, patch
from services.tts import get_audio_url
from tests.conftest import make_words, make_list


# ── Cache hit ──────────────────────────────────────────────────────────────

def test_returns_cached_url_when_file_exists(db, tmp_path):
    audio_file = tmp_path / "cat.mp3"
    audio_file.write_bytes(b"fake mp3")
    db.execute(
        "INSERT INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
        ("cat", str(audio_file), "2025-01-01T00:00:00+00:00"),
    )
    db.commit()

    url = get_audio_url("cat", db)
    assert url == "/" + str(audio_file).replace("\\", "/")


def test_regenerates_when_cached_file_missing(db, tmp_path, mocker):
    """Stale DB entry pointing to a missing file should trigger regeneration."""
    missing_path = str(tmp_path / "missing.mp3")
    db.execute(
        "INSERT INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
        ("cat", missing_path, "2025-01-01T00:00:00+00:00"),
    )
    db.commit()

    def fake_save(path):
        open(path, "wb").write(b"x" * 3000)

    mock_tts = MagicMock()
    mock_tts.return_value.save.side_effect = fake_save
    mocker.patch("services.tts.gTTS", mock_tts)
    mocker.patch("services.tts.AUDIO_DIR", str(tmp_path))

    url = get_audio_url("cat", db)
    assert url is not None


# ── Cache miss ─────────────────────────────────────────────────────────────

def test_generates_and_caches_new_audio(db, tmp_path, mocker):
    def fake_save(path):
        open(path, "wb").write(b"x" * 3000)

    mock_tts = MagicMock()
    mock_tts.return_value.save.side_effect = fake_save
    mocker.patch("services.tts.gTTS", mock_tts)
    mocker.patch("services.tts.AUDIO_DIR", str(tmp_path))

    url = get_audio_url("dog", db)

    assert url is not None
    assert url.endswith(".mp3")
    cached = db.execute("SELECT file_path FROM audio_cache WHERE word_text='dog'").fetchone()
    assert cached is not None


def test_returns_none_on_gtts_failure(db, tmp_path, mocker):
    mocker.patch("services.tts.gTTS", side_effect=Exception("network error"))
    mocker.patch("services.tts.AUDIO_DIR", str(tmp_path))

    url = get_audio_url("fish", db)
    assert url is None


def test_returns_none_when_generated_file_too_small(db, tmp_path, mocker):
    """A suspiciously small file (soft rate-limit response) should be discarded."""
    def fake_save(path):
        open(path, "wb").write(b"x" * 100)

    mock_tts = MagicMock()
    mock_tts.return_value.save.side_effect = fake_save
    mocker.patch("services.tts.gTTS", mock_tts)
    mocker.patch("services.tts.AUDIO_DIR", str(tmp_path))

    url = get_audio_url("bird", db)

    assert url is None
    # File should be cleaned up
    assert not (tmp_path / "bird.mp3").exists()
    # Nothing should be cached
    cached = db.execute("SELECT file_path FROM audio_cache WHERE word_text='bird'").fetchone()
    assert cached is None

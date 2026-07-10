import os
from unittest.mock import MagicMock
from services.tts import get_audio_url, get_sentence_audio_url, _hashed_filename


def make_mock_tts(mocker, tmp_path, size=3000):
    """Patch gTTS so save() writes a fake mp3 of the given size."""
    def fake_save(path):
        open(path, "wb").write(b"x" * size)

    mock_tts = MagicMock()
    mock_tts.return_value.save.side_effect = fake_save
    mocker.patch("services.tts.gTTS", mock_tts)
    mocker.patch("services.tts.AUDIO_DIR", str(tmp_path))
    return mock_tts


# ── Cache hit ──────────────────────────────────────────────────────────────

def test_returns_cached_url_when_file_exists(db, tmp_path, mocker):
    filename = _hashed_filename("cat")
    audio_file = tmp_path / filename
    audio_file.write_bytes(b"fake mp3")
    db.execute(
        "INSERT INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
        ("cat", str(audio_file), "2025-01-01T00:00:00+00:00"),
    )
    db.commit()
    mock_tts = mocker.patch("services.tts.gTTS")

    url = get_audio_url("cat", db)
    assert url == f"/static/audio/{filename}"
    mock_tts.assert_not_called()


def test_legacy_word_named_cache_entry_regenerated(db, tmp_path, mocker):
    """Cache entries from the old scheme (word in the filename, which leaked
    the answer in the page source) are treated as misses and regenerated."""
    legacy_file = tmp_path / "cat.mp3"
    legacy_file.write_bytes(b"fake mp3")
    db.execute(
        "INSERT INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
        ("cat", str(legacy_file), "2025-01-01T00:00:00+00:00"),
    )
    db.commit()
    mock_tts = make_mock_tts(mocker, tmp_path)

    url = get_audio_url("cat", db)

    assert url == f"/static/audio/{_hashed_filename('cat')}"
    assert mock_tts.call_count == 1
    cached = db.execute("SELECT file_path FROM audio_cache WHERE word_text='cat'").fetchone()
    assert os.path.basename(cached["file_path"]) == _hashed_filename("cat")


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
    make_mock_tts(mocker, tmp_path, size=100)

    url = get_audio_url("bird", db)

    assert url is None
    # File should be cleaned up
    assert list(tmp_path.glob("*.mp3")) == []
    # Nothing should be cached
    cached = db.execute("SELECT file_path FROM audio_cache WHERE word_text='bird'").fetchone()
    assert cached is None


def test_url_never_contains_the_word(db, tmp_path, mocker):
    """The mp3 URL appears in the test page source, so it must not spell
    out the word being tested."""
    make_mock_tts(mocker, tmp_path)

    url = get_audio_url("xylophone", db)

    assert "xylophone" not in url
    assert url.startswith("/static/audio/") and url.endswith(".mp3")


def test_word_is_normalised_for_cache_key(db, tmp_path, mocker):
    """'Cat ' and 'cat' should share one cache entry."""
    mock_tts = make_mock_tts(mocker, tmp_path)

    get_audio_url("Cat ", db)
    get_audio_url("cat", db)

    assert mock_tts.call_count == 1
    rows = db.execute("SELECT word_text FROM audio_cache").fetchall()
    assert [r["word_text"] for r in rows] == ["cat"]


# ── Sentence audio ─────────────────────────────────────────────────────────

def test_sentence_audio_generated_and_cached(db, tmp_path, mocker):
    mock_tts = make_mock_tts(mocker, tmp_path)

    url = get_sentence_audio_url("where", "Do you know where my bag is?", db)

    filename = _hashed_filename("__sentence__where", prefix="sentence_")
    assert url == f"/static/audio/{filename}"
    assert "where" not in url  # must not leak the word
    assert (tmp_path / filename).exists()
    # gTTS is called with the sentence, not the word
    assert mock_tts.call_args.kwargs.get("text") == "Do you know where my bag is?"
    cached = db.execute(
        "SELECT file_path FROM audio_cache WHERE word_text='__sentence__where'"
    ).fetchone()
    assert cached is not None


def test_sentence_cache_does_not_collide_with_word_cache(db, tmp_path, mocker):
    mock_tts = make_mock_tts(mocker, tmp_path)

    word_url = get_audio_url("where", db)
    sentence_url = get_sentence_audio_url("where", "Do you know where my bag is?", db)

    assert word_url != sentence_url
    assert mock_tts.call_count == 2
    rows = {r["word_text"] for r in db.execute("SELECT word_text FROM audio_cache").fetchall()}
    assert rows == {"where", "__sentence__where"}


def test_sentence_audio_cache_hit_skips_generation(db, tmp_path, mocker):
    mock_tts = make_mock_tts(mocker, tmp_path)

    get_sentence_audio_url("where", "Do you know where my bag is?", db)
    get_sentence_audio_url("where", "Do you know where my bag is?", db)

    assert mock_tts.call_count == 1


def test_sentence_audio_returns_none_on_failure(db, tmp_path, mocker):
    mocker.patch("services.tts.gTTS", side_effect=Exception("network error"))
    mocker.patch("services.tts.AUDIO_DIR", str(tmp_path))

    assert get_sentence_audio_url("where", "Do you know where my bag is?", db) is None


def test_sentence_audio_discards_tiny_file(db, tmp_path, mocker):
    make_mock_tts(mocker, tmp_path, size=100)

    url = get_sentence_audio_url("where", "Do you know where my bag is?", db)

    assert url is None
    assert list(tmp_path.glob("*.mp3")) == []

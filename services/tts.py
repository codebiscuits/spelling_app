import os
import re
import logging
from datetime import datetime, timezone
from gtts import gTTS

logger = logging.getLogger(__name__)

AUDIO_DIR = os.getenv("AUDIO_DIR", "static/audio")
AUDIO_URL_PREFIX = "/static/audio"


def get_audio_url(word_text: str, db) -> str | None:
    """
    Returns a URL for the word's audio file, generating via gTTS if not cached.
    Returns None on failure.
    """
    word_lower = word_text.lower().strip()
    safe_name = re.sub(r"[^a-z0-9]", "_", word_lower) + ".mp3"
    file_path = os.path.join(AUDIO_DIR, safe_name)
    audio_url = f"{AUDIO_URL_PREFIX}/{safe_name}"

    cached = db.execute(
        "SELECT file_path FROM audio_cache WHERE word_text=?", (word_lower,)
    ).fetchone()
    if cached and os.path.exists(cached["file_path"]):
        return audio_url

    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        tts = gTTS(text=word_text, lang="en", tld="co.uk")
        tts.save(file_path)

        # Guard against soft rate-limit responses: Google sometimes returns a
        # 200 with near-silent minimal audio instead of a proper error.  Any
        # legitimate word audio is several kilobytes; if the file is tiny it
        # is unusable.
        file_size = os.path.getsize(file_path)
        if file_size < 2000:
            logger.warning(
                "TTS output for %r is suspiciously small (%d bytes) — discarding",
                word_text, file_size,
            )
            os.remove(file_path)
            return None

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
            (word_lower, file_path, now),
        )

        return audio_url

    except Exception as e:
        logger.error("TTS failed for %r: %s", word_text, e)
        return None


def get_sentence_audio_url(word_text: str, sentence: str, db) -> str | None:
    """
    Returns a URL for the context-sentence audio file for word_text,
    generating via gTTS if not cached.  Returns None on failure.
    """
    word_lower = word_text.lower().strip()
    cache_key = f"__sentence__{word_lower}"
    safe_name = "sentence_" + re.sub(r"[^a-z0-9]", "_", word_lower) + ".mp3"
    file_path = os.path.join(AUDIO_DIR, safe_name)
    audio_url = f"{AUDIO_URL_PREFIX}/{safe_name}"

    cached = db.execute(
        "SELECT file_path FROM audio_cache WHERE word_text=?", (cache_key,)
    ).fetchone()
    if cached and os.path.exists(cached["file_path"]):
        return audio_url

    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        tts = gTTS(text=sentence, lang="en", tld="co.uk")
        tts.save(file_path)

        file_size = os.path.getsize(file_path)
        if file_size < 2000:
            logger.warning(
                "TTS sentence output for %r is suspiciously small (%d bytes) — discarding",
                word_text, file_size,
            )
            os.remove(file_path)
            return None

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
            (cache_key, file_path, now),
        )

        return audio_url

    except Exception as e:
        logger.error("TTS sentence generation failed for %r: %s", word_text, e)
        return None

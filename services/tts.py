import os
import re
import logging
from datetime import datetime, timezone
from gtts import gTTS

logger = logging.getLogger(__name__)

AUDIO_DIR = "static/audio"


def get_audio_url(word_text: str, db) -> str | None:
    """
    Returns a URL for the word's audio file, generating via gTTS if not cached.
    Returns None on failure.
    """
    word_lower = word_text.lower().strip()

    cached = db.execute(
        "SELECT file_path FROM audio_cache WHERE word_text=?", (word_lower,)
    ).fetchone()
    if cached:
        return "/" + cached["file_path"].replace("\\", "/")

    safe_name = re.sub(r"[^a-z0-9]", "_", word_lower) + ".mp3"
    file_path = os.path.join(AUDIO_DIR, safe_name)

    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        tts = gTTS(text=word_text, lang="en", tld="co.uk")
        tts.save(file_path)

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO audio_cache (word_text, file_path, created_at) VALUES (?,?,?)",
            (word_lower, file_path, now),
        )

        return "/" + file_path.replace("\\", "/")

    except Exception as e:
        logger.error("TTS failed for %r: %s", word_text, e)
        return None

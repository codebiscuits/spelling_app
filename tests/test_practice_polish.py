"""Release 1 polish: 'practice' wording, ten-segment progress, replay button."""

import re

from tests.conftest import (
    current_word,
    setup_practice_list,
    submit_answer,
)

WORDS = ["apple", "banana", "cherry", "dragon", "eleven", "forest", "garden",
         "hammer", "island", "jungle", "kitten", "lemon"]


def start(client):
    setup_practice_list(client.child_id, WORDS)
    client.get("/test/start")


def visible_text(html):
    """Page text with tags, attribute values and URLs removed."""
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def filled_segments(html):
    return len(re.findall(r'class="practice-segment is-done"', html))


# ── Progress display ───────────────────────────────────────────────────────

def test_first_word_shows_practice_1_of_10(child_client):
    start(child_client)
    _, _, resp = current_word(child_client)
    assert "Practice 1 of 10" in resp.text
    assert len(re.findall(r'class="practice-segment( |")', resp.text)) == 10
    assert filled_segments(resp.text) == 0
    assert 'role="progressbar"' in resp.text
    assert 'aria-valuenow="0"' in resp.text
    assert 'aria-valuemax="10"' in resp.text
    assert "is-current" in resp.text


def test_segment_fills_after_word_completed(child_client):
    start(child_client)
    wid, word, _ = current_word(child_client)
    submit_answer(child_client, wid, word)
    _, _, resp = current_word(child_client)
    assert "Practice 2 of 10" in resp.text
    assert filled_segments(resp.text) == 1
    assert 'aria-valuenow="1"' in resp.text


def test_segment_does_not_fill_between_attempts(child_client):
    start(child_client)
    wid, word, _ = current_word(child_client)
    submit_answer(child_client, wid, "wrong")
    _, _, resp = current_word(child_client)  # attempt 2 of the same word
    assert "Practice 1 of 10" in resp.text
    assert filled_segments(resp.text) == 0
    submit_answer(child_client, wid, "wrong again")  # final attempt
    _, _, resp = current_word(child_client)
    assert filled_segments(resp.text) == 1


def test_bonus_word_has_no_ten_segment_display(child_client):
    start(child_client)
    for _ in range(10):
        wid, _, _ = current_word(child_client)
        submit_answer(child_client, wid, "wrong")
        submit_answer(child_client, wid, "wrong")
    child_client.post("/test/topup")
    resp = child_client.get("/test/word")
    assert "Bonus word" in resp.text
    assert "practice-segment" not in resp.text
    assert "of 10" not in resp.text


# ── Hear the word again ────────────────────────────────────────────────────

def test_attempt_1_has_no_replay_button(child_client):
    start(child_client)
    _, _, resp = current_word(child_client)
    assert "Hear the word again" not in resp.text


def test_attempt_2_has_replay_button_hidden_until_word_hidden(child_client):
    start(child_client)
    wid, word, _ = current_word(child_client)
    submit_answer(child_client, wid, "wrong")
    _, _, resp = current_word(child_client)
    assert "Hear the word again" in resp.text
    # Initially hidden; the "I'm Ready" JS reveals it after the word is hidden
    assert re.search(r'id="replay-btn"[^>]*display:none', resp.text)
    assert 'id="word-audio"' in resp.text
    # The audio URL is a hash, not the spelling
    src = re.search(r'id="word-audio" src="([^"]+)"', resp.text).group(1)
    assert word not in src


def test_replay_button_still_hides_spelling_after_js_hide(child_client):
    """The static JS reveals the replay button inside the ready handler."""
    js = open("static/js/spelling.js").read()
    ready = js.split("readyBtn.addEventListener")[1].split("});")[0]
    assert "wordDisplay.style.display = 'none'" in ready
    assert "replayBtn.style.display" in ready


# ── No child-facing "test" ─────────────────────────────────────────────────

def test_child_pages_never_say_test(child_client):
    pages = [child_client.get("/child/dashboard").text]
    start(child_client)
    pages.append(child_client.get("/test/word").text)
    wid, _, _ = current_word(child_client)
    submit_answer(child_client, wid, "wrong")
    pages.append(child_client.get("/test/word").text)  # attempt 2
    for _ in range(12):
        r = child_client.get("/test/word", follow_redirects=False)
        if r.status_code == 303:
            break
        wid, _, _ = current_word(child_client)
        submit_answer(child_client, wid, "wrong")
    pages.append(child_client.get("/test/topup").text)
    pages.append(child_client.get("/test/results").text)
    for html in pages:
        titles = re.findall(r"<title>(.*?)</title>", html, flags=re.S)
        text = visible_text(html) + " ".join(titles)
        assert not re.search(r"\btests?\b", text, flags=re.I), text

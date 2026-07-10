"""Browser end-to-end test: login → spelling test → results.

Runs a real uvicorn server on a temp database and drives it with
Playwright, exercising static/js/spelling.js (audio button, input reveal,
form submit) which the TestClient suite cannot reach.

Excluded from the default run; execute with:  uv run pytest -m e2e
"""

import os
import socket
import sqlite3
import subprocess
import sys
import time

import bcrypt
import httpx
import pytest

from services.tts import _hashed_filename

pytestmark = pytest.mark.e2e

PASSWORD = "correct horse"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    db_path = tmp / "e2e.db"
    audio_dir = tmp / "audio"
    audio_dir.mkdir()
    port = free_port()

    env = {
        **os.environ,
        "DB_PATH": str(db_path),
        "AUDIO_DIR": str(audio_dir),
        "SECRET_KEY": "e2e-secret",
        "HTTPS_ONLY": "false",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD_HASH": "",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 20
        while True:
            try:
                if httpx.get(f"{base_url}/login").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.time() > deadline:
                raise RuntimeError("Server did not start")
            time.sleep(0.2)

        # Seed a child with a one-word list, with the audio pre-cached so
        # the server never calls out to gTTS
        con = sqlite3.connect(db_path)
        password_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
        child_id = con.execute(
            "INSERT INTO users (name, dob, password_hash, date_created, is_admin) VALUES (?,?,?,?,0)",
            ("Alice", "2017-06-01", password_hash, "2025-01-01T00:00:00+00:00"),
        ).lastrowid
        list_id = con.execute(
            "INSERT INTO word_lists (name, year_group) VALUES ('E2E', NULL)"
        ).lastrowid
        con.execute("INSERT INTO words (word, list_id) VALUES ('zebra', ?)", (list_id,))
        con.execute(
            "INSERT INTO user_list_unlocks (user_id, list_id, unlocked_at) VALUES (?,?,'2025-01-01')",
            (child_id, list_id),
        )
        audio_file = audio_dir / _hashed_filename("zebra")
        audio_file.write_bytes(b"\x00" * 3000)
        con.execute(
            "INSERT INTO audio_cache (word_text, file_path, created_at) VALUES ('zebra', ?, '2025-01-01')",
            (str(audio_file),),
        )
        con.commit()
        con.close()

        yield base_url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_child_completes_a_spelling_test(server):
    playwright_api = pytest.importorskip("playwright.sync_api")

    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Login
        page.goto(f"{server}/login")
        page.fill("#username", "Alice")
        page.fill("#password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/child/dashboard")
        assert "Alice" in page.text_content("h1")

        # Start a test
        page.click("text=Start a Spelling Test")
        page.wait_for_url("**/test/word")

        # Attempt 1: input hidden until Play is clicked; word not in the page
        assert "zebra" not in page.content()
        assert not page.is_visible("#answer")
        page.click("#play-btn")
        page.wait_for_selector("#answer", state="visible")

        # Empty submissions are blocked client-side
        page.click("button[type=submit]")
        page.wait_for_url("**/test/word")  # still on the same page

        # Answer correctly
        page.fill("#answer", "zebra")
        page.click("button[type=submit]")

        # One-word test → straight to results with full first-try marks
        page.wait_for_url("**/test/results")
        assert "Test Complete!" in page.content()
        assert page.text_content(".score-number").strip() == "2"

        browser.close()

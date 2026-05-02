"""
Capture still-frame thumbnails of every mini-game for the game picker.

Requirements:
  uv add --dev playwright
  uv run playwright install chromium

Usage (with dev server already running on port 8000):
  uv run python scripts/capture_thumbnails.py
"""

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright not installed — run: uv add --dev playwright && uv run playwright install chromium")

BASE_URL = "http://localhost:8000"
MINI_GAMES_DIR = Path(__file__).parent.parent / "mini_games"
OUTPUT_DIR = Path(__file__).parent.parent / "static" / "img" / "game-thumbs"
VIEWPORT = {"width": 600, "height": 450}


def simulate_interaction(page):
    """Click and move the mouse across the canvas to trigger games that need input.

    Returns with the mouse button still held down at the canvas centre so
    that games like Lightning (which only render while held) are active at
    screenshot time. The caller must call page.mouse.up() after screenshotting.
    """
    w, h = VIEWPORT["width"], VIEWPORT["height"]
    # Click a grid of points — bias toward the upper half so firework rockets
    # have a short travel distance and explode quickly
    positions = [
        (w * x // 4, h * y // 6)
        for x in range(1, 4)
        for y in range(1, 4)
    ]
    for x, y in positions:
        page.mouse.move(x, y)
        page.mouse.down()
        page.wait_for_timeout(30)
        page.mouse.up()
        page.wait_for_timeout(20)

    # Sweep across the centre to trigger mousemove-driven effects
    for step in range(10):
        page.mouse.move(w * step // 10, h // 2)
        page.wait_for_timeout(20)

    # Park mouse at centre with button held so held-down effects (e.g. lightning
    # bolts) are active when the screenshot is taken
    page.mouse.move(w // 2, h // 2)
    page.mouse.down()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    game_files = sorted(MINI_GAMES_DIR.glob("*.html"))
    if not game_files:
        sys.exit(f"No HTML files found in {MINI_GAMES_DIR}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        for html_file in game_files:
            url = f"{BASE_URL}/mini-games/{html_file.name}"
            out_path = OUTPUT_DIR / html_file.with_suffix(".png").name
            print(f"  {html_file.name} → {out_path.name}", end="", flush=True)
            try:
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(300)   # let initial frame render
                simulate_interaction(page)   # ends with mouse held at centre
                page.wait_for_timeout(400)   # catch peak of animations
                page.screenshot(path=str(out_path))
                page.mouse.up()
                print(" ✓")
            except Exception as exc:
                print(f" ✗ ({exc})")
        browser.close()

    print(f"\nDone — {len(game_files)} thumbnails saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

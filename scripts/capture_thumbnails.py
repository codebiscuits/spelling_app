"""
Capture still-frame thumbnails of the mini-games for the game picker.

Every game in MINI_GAMES needs static/img/game-thumbs/<name>.png, and
tests/test_templates_env.py fails when one is missing. Run this after
adding a game, then commit the new PNG with it.

The script serves the game files itself, straight from GAME_DIRS, so the
app does not need to be running and no login is needed.

Requirements:
  uv add --dev playwright
  uv run playwright install chromium

Usage:
  uv run python scripts/capture_thumbnails.py              # games with no thumbnail yet
  uv run python scripts/capture_thumbnails.py spider_web.html  # named games only
  uv run python scripts/capture_thumbnails.py --all        # every game again

Set CHROMIUM=/path/to/chrome to use a browser already on the machine.
"""

import argparse
import functools
import http.server
import math
import os
import sys
import threading
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright not installed: run uv add --dev playwright && uv run playwright install chromium")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # game_path() resolves GAME_DIRS from the repo root

from templates_env import MINI_GAMES, game_path  # noqa: E402

OUTPUT_DIR = ROOT / "static" / "img" / "game-thumbs"
VIEWPORT = {"width": 600, "height": 450}


def thumb_path(game):
    return OUTPUT_DIR / game["file"].replace(".html", ".png")


def simulate_interaction(page):
    """Click and move the mouse across the canvas to trigger games that need input.

    Used for classic games, which mostly start blank. Returns with the mouse
    button still held down at the canvas centre so that games like Lightning
    (which only render while held) are active at screenshot time. The caller
    must call page.mouse.up() after screenshotting.
    """
    w, h = VIEWPORT["width"], VIEWPORT["height"]
    # Click a grid of points, biased toward the upper half so firework rockets
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


def paint_loops(page, loops=3):
    """Left-drag a few loops round the centre, for games that start blank."""
    w, h = VIEWPORT["width"], VIEWPORT["height"]
    for k in range(loops):
        r = 50 + k * 45
        page.mouse.move(w / 2 + r, h / 2)
        page.mouse.down()
        for step in range(1, 41):
            a = step / 40 * 2 * math.pi
            page.mouse.move(w / 2 + r * math.cos(a), h / 2 + r * math.sin(a) * 0.8)
            page.wait_for_timeout(15)
        page.mouse.up()


def plant_torches(page):
    """Shadow Maze is dark until lit: walk the lantern about and click to
    plant its four torches."""
    w, h = VIEWPORT["width"], VIEWPORT["height"]
    for fx, fy in ((0.25, 0.3), (0.7, 0.3), (0.3, 0.7), (0.75, 0.7)):
        page.mouse.move(w * fx, h * fy, steps=8)
        page.mouse.click(w * fx, h * fy)
        page.wait_for_timeout(150)
    page.mouse.move(w / 2, h / 2, steps=8)


def still(page):
    """No input: the game's opening scene is the picture."""


# Reward games whose opening scene needs something other than a breeze.
REWARD_STEPS = {
    "mandala.html": paint_loops,             # starts as an empty canvas
    "reaction_diffusion.html": paint_loops,  # starts with a few small spots
    "shadow_maze.html": plant_torches,       # dark apart from the lantern
    "topple_tower.html": still,             # mouse movement pushes the tower over
}


def capture_reward(page, game):
    """Reward games open on a ready-made scene, and a click means different
    things in each (draw, spin, flick). So by default only move the mouse,
    which most of them answer with a gentle effect, and let the scene settle."""
    w, h = VIEWPORT["width"], VIEWPORT["height"]
    page.wait_for_timeout(1500)
    steps = REWARD_STEPS.get(game["file"])
    if steps:
        steps(page)
    else:
        for step in range(12):
            page.mouse.move(w * (2 + step) // 16, h * 2 // 3)
            page.wait_for_timeout(40)
    page.wait_for_timeout(1500)


# Reward games put a controls pane and buttons over the play area. At
# thumbnail size they hide the game. So keep only the drawing surfaces that
# fill most of the window, and the elements that hold them, and hide the rest.
# A small canvas inside a pane (Particle Life's colour grid) is hidden too.
HIDE_OVERLAYS = """() => {
  const big = [...document.querySelectorAll('canvas, svg')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width * r.height >= 0.5 * innerWidth * innerHeight;
  });
  for (const el of document.body.querySelectorAll('*')) {
    if (big.some(s => s === el || s.contains(el) || el.contains(s))) continue;
    el.style.visibility = 'hidden';
  }
}"""


def serve(directory):
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("files", nargs="*", help="game files to capture, e.g. spider_web.html")
    parser.add_argument("--all", action="store_true", help="capture every game, even with a thumbnail")
    args = parser.parse_args()

    by_file = {g["file"]: g for g in MINI_GAMES}
    unknown = [f for f in args.files if f not in by_file]
    if unknown:
        sys.exit(f"Not in MINI_GAMES: {', '.join(unknown)}")
    if args.files:
        games = [by_file[f] for f in args.files]
    elif args.all:
        games = list(MINI_GAMES)
    else:
        games = [g for g in MINI_GAMES if not thumb_path(g).exists()]
    if not games:
        print("Every game already has a thumbnail. Use --all to capture them again.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = serve(ROOT)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    failed = 0
    with sync_playwright() as p:
        # CHROMIUM names a browser to use instead of the one Playwright downloads.
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        for game in games:
            out_path = thumb_path(game)
            print(f"  {game['file']} → {out_path.name}", end="", flush=True)
            path = game_path(game["file"])
            if not path:
                print(" ✗ (file not found in GAME_DIRS)")
                failed += 1
                continue
            # A fresh page each time, so one game's audio or timers cannot leak into the next.
            page = browser.new_page(viewport=VIEWPORT)
            try:
                page.goto(f"{base}/{path}", wait_until="networkidle")
                page.wait_for_timeout(300)   # let initial frame render
                if game["tier"] == "reward":
                    capture_reward(page, game)
                    page.evaluate(HIDE_OVERLAYS)
                    page.wait_for_timeout(100)
                    page.screenshot(path=str(out_path))
                else:
                    simulate_interaction(page)   # ends with mouse held at centre
                    page.wait_for_timeout(400)   # catch peak of animations
                    page.screenshot(path=str(out_path))
                    page.mouse.up()
                print(" ✓")
            except Exception as exc:
                print(f" ✗ ({exc})")
                failed += 1
            finally:
                page.close()
        browser.close()
    server.shutdown()

    print(f"\nDone: {len(games) - failed} of {len(games)} thumbnails saved to {OUTPUT_DIR}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

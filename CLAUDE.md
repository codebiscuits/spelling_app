# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A web-based practice app for primary school children, with two subjects: spelling and times tables. In spelling, children listen to a word, type their spelling, and receive immediate feedback. In times tables, children answer multiplication and division questions with clues after a wrong answer. Child-facing pages say "practice", never "test". The app picks the next items for each child from their own results, awards badges, medals, and trophies, and gives reward mini-games. Admins see progress charts for each child.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLite (raw parameterised SQL, no ORM) |
| Frontend | Jinja2 templates, vanilla JS, no build step |
| Audio | gTTS (no API key required), British accent (`tld="co.uk"`) |
| Charts | Chart.js via CDN |
| Sessions | Starlette `SessionMiddleware` (signed cookies) |
| Passwords | bcrypt |
| Package management | uv |

## Running the app

```bash
uv run uvicorn main:app --reload
```

Requires a `.env` file — see `SETUP.md`.

## Key architectural decisions

- **Shared Jinja2 instance** — `templates_env.py` holds the single `Jinja2Templates` instance imported by all routers. Never create a separate instance in a router; Jinja2 globals (e.g. `current_palette`, `static_version`) are set on this shared instance and would be invisible to any other.
- **New-style TemplateResponse API** — always use `templates.TemplateResponse(request, "name.html", context)` with `request` as a positional argument, not inside the context dict.
- **uv for everything** — use `uv add` to install packages and `uv run` to run scripts. Never use `pip`.
- **No ORM** — all database access uses raw parameterised SQL via the `sqlite3` module.
- **No async for gTTS** — gTTS is synchronous; keep TTS calls and their callers synchronous.
- **Static file cache-busting** — `static_version(path)` in `templates_env.py` returns the file's mtime as a query string (e.g. `?v=1234567890`). Use it on all local JS/CSS `<link>`/`<script>` tags so browsers pick up changes without a hard refresh.

## Project structure

```
spelling_app/
├── main.py                  # App factory, middleware, login/logout, /mini-games/{file} (launch nonce check)
├── database.py              # Schema, get_db(), init_db(), additive migrations
├── auth.py                  # Password hashing, session guards, CSRF
├── templates_env.py         # Shared Jinja2 instance, colour palettes, MINI_GAMES list, static_version()
├── routers/
│   ├── admin.py             # /admin/*: word lists, children, game unlocks
│   ├── admin_progress.py    # /admin/progress, /admin/children/{id}/spelling and /arithmetic: read-only charts and evidence
│   ├── arithmetic.py        # /arithmetic/*: start, question, feedback, topup, results
│   ├── child.py             # /child/*: dashboard, game wrapper (POST /child/games/{file})
│   └── spelling.py          # /test/* — start, word, topup, results
├── services/
│   ├── tts.py               # gTTS audio generation with file caching; get_audio_url() + get_sentence_audio_url()
│   ├── spelling_progression.py   # Per-word selection: focus, weak, stale; list unlocking
│   ├── progression_backfill.py   # One-time release 2 backfill of silent medals and trophies
│   ├── arithmetic_facts.py       # Times-tables facts, families, ladder, clues (incl. SVG division diagram)
│   ├── arithmetic_progression.py # Per-direction selection with family focus; rung unlocking
│   ├── gamification.py      # Badge, medal, and trophy rules for both subjects
│   ├── game_rewards.py      # Reward-game unlocks: only every 3rd badge unlocks the next game
│   ├── game_activity.py     # Game credits, plays, launch nonces, recent-games picker (offer_games)
│   └── progress_monitoring.py    # Read-only queries behind the admin progress pages
├── seed/
│   └── curriculum_words.py  # UK National Curriculum word lists + homophone context sentences (idempotent)
├── static/
│   ├── css/style.css
│   ├── js/                  # spelling.js, arithmetic.js, admin_progress.js
│   ├── img/                 # SVG icons: badge, medal, trophy, favicon
│   └── audio/               # Cached .mp3 files (git-ignored)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── child/               # dashboard, test, topup, results, game, arithmetic_question, arithmetic_feedback
│   └── admin/               # dashboard, child_detail, edit_child, word_lists, edit_word_list, progress_overview, progress_subject, progress_practice, progress_item
├── tests/                   # pytest suite (unit, route and migration tests; one Playwright e2e)
└── mini_games/              # Standalone HTML canvas games (served by a route, not as plain static files)
```

## Spelling practice

`services/spelling_progression.py` chooses the ten words of an ordinary practice. It replaced the old weighted sampling (`services/word_selection.py` no longer exists).

- **Order.** Lists and words have explicit `position` columns (`word_lists.position`, `words.position`). A child meets words in curriculum order, one new word at a time.
- **Evidence.** Only an *ordinary first attempt* (`spelling_attempts.attempt_number=1`) counts. Second attempts (2) and top-ups (3) never do.
- **Mastered.** The latest three ordinary first attempts at the word are all correct.
- **Focus word.** One word is introduced at a time (`spelling_focus`). It appears in every practice until it has three first-try-correct appearances in a row since it became focus.
- **Ten slots.** 1 focus + 5 weak + 4 stale. Weak means seen, not mastered, with at least 5 first attempts, lowest recent accuracy first. Stale means mastered, longest since practice first. When nothing is left to introduce, the slots are 6 weak + 4 stale. Empty slots are filled from other seen words. A locked word is never chosen.
- **First practice.** A child with no attempts gets the ten earliest words.
- **Lists.** A child with no lists gets the earliest list. When every word in the child's available lists has been introduced, the next list in curriculum order unlocks.
- **Practice flow.** The test page shows a ten-segment progress bar (`role="progressbar"`). On attempt 2 the word is shown, then hidden, and a "Hear the word again" button plays it.

## Times tables practice

`routers/arithmetic.py` (`/arithmetic/start`, `/question`, `/feedback`, `/topup`, `/results`) mirrors the spelling flow. `static/js/arithmetic.js` sends the response time.

- **Facts.** Factors 2 to 12. No ×0, ÷0, ×1 or ÷1. A *direction* is one exact question (`m:3x4`, `d:12/3`). A *family* is the unordered pair of factors: four directions, or two for a square. All facts are generated in `services/arithmetic_facts.py`.
- **Ladder.** Tables open in rungs: (2, 10), 5, 4, 3, 6, 8, 9, 7, 11, 12 (`arithmetic_rungs`). The next rung opens when every direction of the latest rung is secure. Opened rungs never lock.
- **Secure.** The latest three ordinary first attempts are correct (as for spelling).
- **Focus is a family** (`arithmetic_focus`). Each direction leaves the focus slots on its own after three first-try-correct appearances in a row. The family stays focus until all directions have left.
- **Slots.** Weak + stale: 3 + 3 for a family of four, 4 + 4 for a square, 6 + 4 with no focus. Each direction that leaves focus frees a slot for weak. The first practice is whole rung 1 families in fixed order (2×2, 2×3 and 2×4, ten questions).
- **Clues.** After a wrong first answer, the child sees a clue and has a second try. A multiplication clue counts up in the second factor and never prints the answer. A division clue is text plus an inline SVG diagram of counters in equal groups. After a second wrong answer, `/arithmetic/feedback` shows the completed fact.
- **Response time.** The browser measures it. The server clamps it and falls back to its own clock (`response_ms`).
- **Sessions.** Practices are `test_sessions` rows with `subject='arithmetic'`. Attempts are in `arithmetic_attempts`.
- **Top-ups.** Same rules as spelling. Never an unseen direction.

## Gamification

Badges, medals and trophies are in `services/gamification.py`. Both subjects use the same badge table and game rules.

| Award | Condition | Frequency |
|---|---|---|
| Badge | Final practice score ≥ 16/20 | At most once per child per Europe/London day, across both subjects |
| Medal | Every 10 distinct items first mastered (words, or times-tables directions) | Once per threshold. An item counts once, ever (`first_mastered`, `milestone_medals`) |
| Trophy | The first ordinary first attempt at a word from a list (spelling), or at a direction on a rung (arithmetic) | Once per list or rung (`start_trophies`) |

- **Reward games.** Only every third badge unlocks the next reward game (`services/game_rewards.py`, `BADGE_STEP = 3`). Medals and trophies never unlock games. Old `user_game_unlocks` rows may say `medal` or `trophy` as their source.
- **Release 2 backfill.** `services/progression_backfill.py` awarded earlier medals and trophies silently (`silent=1`), so there were no banners and no game unlocks.
- Awards are computed on `/test/results` and `/arithmetic/results`, after `refresh_focus()` closes any finished focus.

After the 10-question practice, a child scoring below 20 may top up: one bonus item at a
time (+1 point each, single attempt, capped at 20). Items missed this practice come
first, then the weakest, then the stalest seen items. Bonus attempts are recorded with
`attempt_number=3` so they never count as evidence, but the topped-up final score does
count toward the badge.

## Game credits and the games picker

`services/game_activity.py` owns all of this. `offer_games()` runs on both results pages.

- **Credit.** A practice scoring 10 or more (`QUALIFYING_SCORE`) banks one credit in `user_game_credits`. A lower score forfeits any unspent credit. README.md and SETUP.md state this threshold, so update them if you change it.
- **Play.** `POST /child/games/{file}` (CSRF checked) consumes one credit, records the play in `user_game_plays`, and returns the wrapper page. Play time is 60 s at 10/20, +6 s per extra point, capped at 120 s.
- **Launch nonce.** The game iframe URL carries a single-use nonce (`user_game_launches`, valid 5 minutes). `GET /mini-games/{file}` serves a child a game file only with a valid nonce. Admins need none. Credit state is never in the session cookie.
- **Picker.** Games played in the last 30 days are listed first. The rest are under "All games". Classic games are always available. Reward games appear once unlocked. A mystery card shows the badges left until the next unlock.

## Admin progress pages

`routers/admin_progress.py` and `services/progress_monitoring.py` are read-only and admin-only. They need no schema change and use the same "mastered" and "secure" rules as the selectors.

- `/admin/progress`: overview of all children, with a Charts column that links to each child's pages.
- `/admin/children/{id}/spelling` and `/arithmetic`: Chart.js charts (`static/js/admin_progress.js`), practice history and item list.
- `/admin/children/{id}/spelling/practices/{session_id}` and `/arithmetic/practices/{session_id}`: per-practice evidence.
- `/admin/children/{id}/spelling/words/{word_id}` and `/arithmetic/facts?key=...`: per-item detail.
- A practice is charted only when it holds at least 10 ordinary first attempts. Shorter practices are listed but not charted.

## Homophone support

Words with homophones have a `context_sentence` TEXT column in the `words` table (added via `ALTER TABLE` migration in `init_db()`). The seed script populates this for ~34 curriculum words (e.g. *where*, *eight*, *reign*). During a practice, `spelling.py` calls `get_sentence_audio_url(word, sentence, db)` to generate and cache a sentence MP3 (cache key: `__sentence__<word>`). The test template shows a "Hear it in a sentence" button only on attempt 1 when a sentence URL is available.

Audio filenames are SHA-256 hashes (`services/tts.py: _hashed_filename()`), never the word itself — the mp3 URL appears in the attempt-1 page source, and a readable filename would reveal the spelling. Cache entries whose stored filename doesn't match the hashed scheme are treated as stale and regenerated.

## Testing

```bash
uv run pytest              # unit + route tests (fast, no network; gTTS is faked)
uv run pytest -m e2e       # Playwright browser test (needs chromium installed)
```

Route tests use the fixtures in `tests/conftest.py` (`client`, `admin_client`, `child_client`) which run the app against a temp database with gTTS mocked. A core invariant covered by `tests/test_spelling_flow.py`: on attempt 1 the word must never appear anywhere in the page source, including audio URLs.

## Mini-games

Standalone single-file HTML canvas toys in `mini_games/`, served as static files. Design standards are codified in `mini_games/HANDBOOK.md` §0 (House standards) and are mandatory for every game:

- **Mouse-first, no touch support** — games are played on a desktop with a mouse, never a touch screen. Every game must give a distinct job to mouse movement, the left button, the right button, and the scroll wheel.
- **Keyboard controls are optional** — add them only when they make the game more fun (extra parameters the mouse can't carry); never put core interactions on the keyboard.
- **Controls pane** — every game shows a frosted-glass panel fixed at the top-left listing every control and what it does, plus live state values.
- **Reset button** — every game has a visible button (bottom-centre pill) that returns the simulation to its initial state without reloading the page.

## Colour palettes

Seven palettes defined in `templates_env.py` (one per weekday). The active palette is injected into CSS variables via a Fisher-Yates shuffle in `base.html`.

## Deployment and staging

**Anything pushed to `main` goes live to children within 60 seconds.** Never push to `main` without Ross's say-so. Work on a branch and test it on staging first. See `SETUP.md` for the full steps.

- **Live.** The fileserver runs the system service `spelling-app` on port 8000. A user timer, `spelling-app-update.timer`, runs `scripts/update.sh` every minute. When `origin/main` has moved, the script runs `git pull origin main`, `uv sync --no-dev`, and restarts the service. That script is in the fileserver checkout (`~/Apps/spelling_app`) and is not tracked in this repo.
- **Staging.** A second checkout at `~/Apps/spelling_app_staging` on the fileserver, branch `staging`, port 8010 on the Tailscale address, with its own `staging.db` (a copy of the newest nightly snapshot). Deploy with `git push -f staging <branch>:staging`, then `ssh fileserver ~/machine-setup/fileserver/spelling-staging.sh restart`. `spelling-staging.sh refresh-db` reloads the data from the newest snapshot. The install and protection scripts are in the separate machine-setup repo, not here. See its `fileserver/README.md`.
- **Before each go-live.** Take a snapshot on the fileserver with `systemctl --user start app-db-backup.service`. Migrations must be additive only (new tables and columns, never a changed or dropped one), so reverting the code needs no database restore.

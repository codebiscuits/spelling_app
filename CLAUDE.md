# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A web-based spelling practice app for primary school children. Children listen to a word, type their spelling, and receive immediate feedback. The app tracks progress, awards badges, medals, and trophies, and unlocks new word lists as children demonstrate mastery.

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

- **Shared Jinja2 instance** — `templates_env.py` holds the single `Jinja2Templates` instance imported by all routers. Never create a separate instance in a router; Jinja2 globals (e.g. `current_palette`) are set on this shared instance and would be invisible to any other.
- **New-style TemplateResponse API** — always use `templates.TemplateResponse(request, "name.html", context)` with `request` as a positional argument, not inside the context dict.
- **uv for everything** — use `uv add` to install packages and `uv run` to run scripts. Never use `pip`.
- **No ORM** — all database access uses raw parameterised SQL via the `sqlite3` module.
- **No async for gTTS** — gTTS is synchronous; keep TTS calls and their callers synchronous.

## Project structure

```
spelling_app/
├── main.py                  # App factory, middleware, login/logout routes
├── database.py              # Schema, get_db(), init_db()
├── auth.py                  # Password hashing, session guards, CSRF
├── templates_env.py         # Shared Jinja2 instance, colour palettes, MINI_GAMES list
├── routers/
│   ├── admin.py             # /admin/* — word lists, children, progress
│   ├── child.py             # /child/* — dashboard, pick list, game wrapper
│   └── spelling.py          # /test/* — start, word, results
├── services/
│   ├── tts.py               # gTTS audio generation with file caching
│   ├── word_selection.py    # Weighted adaptive word sampling
│   └── gamification.py      # Badge, medal, trophy, and list unlock logic
├── seed/
│   └── curriculum_words.py  # UK National Curriculum word lists (idempotent)
├── static/
│   ├── css/style.css
│   ├── js/spelling.js
│   ├── img/                 # SVG icons: badge, medal, trophy, favicon
│   └── audio/               # Cached .mp3 files (git-ignored)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── child/               # dashboard, pick_list, test, results, game
│   └── admin/               # dashboard, child_detail, edit_child, word_lists, edit_word_list
└── mini_games/              # Standalone HTML canvas games (served as static files)
```

## Gamification

| Award | Condition | Frequency |
|---|---|---|
| Badge ⭐ | Session score ≥ 16/20 | Every qualifying session |
| Medal 🏅 | ≥ 50% of list words spelled correctly first-try (cumulative) | Once per list |
| Trophy 🏆 | ≥ 95% first-try correct + all remaining words second-try correct (cumulative) | Once per list; also unlocks next year group |

## Colour palettes

Seven palettes defined in `templates_env.py` (one per weekday). The active palette is injected into CSS variables via a Fisher-Yates shuffle in `base.html`.

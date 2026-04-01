# Spelling App

A web-based spelling practice app for primary school children. Children listen to a word, type their spelling, and receive immediate feedback. The app tracks progress, awards badges, and unlocks new word lists as children demonstrate mastery.

## Features

- **Audio-first testing** — words are read aloud using text-to-speech; no reading required to take a test
- **Two-attempt scoring** — 2 points for first-try correct, 1 point for second-try correct; on a second attempt the word is shown visually so the child can study it
- **Adaptive word selection** — words the child struggles with appear more frequently; unseen words are prioritised over well-known ones
- **Badges, medals, and trophies** — awarded as children improve; earning a trophy unlocks the next year group's word list
- **Progress tracking** — per-list progress bars on the child dashboard show first-try and second-try mastery at a glance
- **Mini game rewards** — scoring 16/20 or higher unlocks a 60-second interactive canvas game as a reward
- **Admin interface** — manage children, word lists, and view detailed per-child performance stats
- **UK National Curriculum word lists** — Years 1–2, 3–4, and 5–6 lists seeded automatically on first run
- **Daily colour palettes** — the UI colour scheme rotates through 7 palettes, one per day of the week

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLite (raw SQL, no ORM) |
| Frontend | Jinja2 templates, vanilla JS, no build step |
| Audio | gTTS (Google Text-to-Speech, no API key required) |
| Charts | Chart.js via CDN |
| Sessions | Starlette `SessionMiddleware` (signed cookies) |
| Passwords | bcrypt |
| Package management | uv |

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Internet connection (for gTTS audio generation; audio is cached after first use)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/codebiscuits/spelling_app.git
cd spelling_app
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Create a `.env` file

Run the setup script, passing your chosen admin password:

```bash
bash setup_env.sh
```

This generates a secure `.env` with a random secret key, hashed password, and correct permissions. Alternatively, copy `.env.example` and fill in the values manually — see `SETUP.md` for instructions.

### 4. Run the server

```bash
uv run uvicorn main:app --reload
```

The app is available at [http://localhost:8000](http://localhost:8000).

On first startup the database is created automatically and seeded with the UK National Curriculum word lists.

## Usage

### Admin

Log in at `/login` with the credentials set in `.env`. From the admin dashboard you can:

- **Add children** — set name, date of birth, password, and which word lists they can access
- **Manage word lists** — create custom lists, add/remove words, set year group
- **View child progress** — test history, per-word performance stats, badge status, score chart
- **Unlock lists manually** — grant a child access to any list at any time
- **Warm the audio cache** — pre-generate audio for all words so children don't experience delays mid-test

### Children

Children log in with their name and password. From their dashboard they can:

- Start a spelling test from any unlocked word list
- View their progress bars showing how many words they have mastered
- See recent test scores
- Play a mini game (only available after scoring ≥ 16/20 on a test)

### Test flow

1. A word is read aloud — the child clicks **Play Word** to hear it
2. The child types their spelling and submits
3. If correct, a "Well done!" message appears on the next word
4. If wrong, the word is shown on screen; the child clicks **I'm Ready — Hide Word** then types it again
5. After 10 words, results are shown with a full breakdown
6. Scoring ≥ 16/20 unlocks a mini game reward

## Scoring and progression

| Result | Points |
|---|---|
| Correct on first attempt | 2 |
| Correct on second attempt | 1 |
| Wrong on both attempts | 0 |
| **Maximum per test** | **20** |

### Badges, medals, and trophies

| Award | Condition | Frequency |
|---|---|---|
| ⭐ Badge | Session score ≥ 16/20 | Every qualifying session |
| 🏅 Medal | ≥ 50% of the list's words spelled correctly first-try (cumulative, across all sessions) | Once per list |
| 🏆 Trophy | ≥ 95% of words first-try correct + all remaining words second-try correct (cumulative) | Once per list |

### List unlock

The next year group's lists unlock automatically when a child earns a **trophy** for the current list:
- ≥ 95% of words spelled correctly on the **first attempt** (at least once, across any session)
- All remaining words spelled correctly on the **second attempt** at least once

This ensures children are genuinely ready before moving on.

## Project structure

```
spelling_app/
├── main.py                  # App factory, middleware, login/logout routes
├── database.py              # Schema, get_db(), init_db()
├── auth.py                  # Password hashing, session guards, CSRF
├── templates_env.py         # Shared Jinja2 instance, colour palettes, game list
├── routers/
│   ├── admin.py             # /admin/* — word lists, children, progress
│   ├── child.py             # /child/* — dashboard, pick list, game wrapper
│   └── spelling.py          # /test/* — start, word, results
├── services/
│   ├── tts.py               # gTTS audio generation with file caching
│   ├── word_selection.py    # Weighted adaptive word sampling
│   └── gamification.py      # Badge, trophy, and list unlock logic
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

## Security

- All passwords hashed with bcrypt
- Session cookies are signed (`SessionMiddleware` with a secret key)
- CSRF tokens on every POST form
- All SQL queries use parameterised statements
- TTS filenames sanitised with a regex allowlist before writing to disk
- Set `HTTPS_ONLY=true` in `.env` for production deployments

## License

MIT

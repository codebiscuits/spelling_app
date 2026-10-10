# Spelling App

A web-based practice app for primary school children, with two subjects: spelling and times tables. Children listen to a word and type it, or answer a times-tables question, and get immediate feedback. The app picks what each child practises next from their own results, awards badges, medals, and trophies, and gives a mini game as a reward.

## Features

- **Audio-first spelling practice**: words are read aloud using text-to-speech; no reading required. A **Hear the word again** button plays the word on the second attempt.
- **Context sentences for homophones** — words with common homophones (e.g. *where/wear*, *eight/ate*, *symbol/cymbal*) show a "Hear it in a sentence" button so children can disambiguate before spelling
- **Two-attempt scoring**: 2 points for first-try correct, 1 point for second-try correct; on a second attempt the word (or a clue) is shown so the child can learn from it
- **Ten-segment progress bar**: shows how far through a practice the child is
- **Per-word progression**: one new word is introduced at a time, in curriculum order, and mixed with the child's weakest and least recently practised words
- **Times tables practice**: tables 2 to 12 as multiplication and division, opened in a fixed order, with clues (including a picture for division) after a wrong answer
- **Badges, medals, and trophies**: a badge for a high score, a medal for every 10 items mastered, a trophy for mastering every word in a list or every question of a times table, kept in a trophy cabinet on the dashboard
- **Mini game rewards**: a practice scoring 10/20 or higher earns one play of a mini game. Every third badge unlocks a new game
- **Recent games first**: the games a child played in the last 30 days are listed first
- **Admin interface**: manage children and word lists, and see progress charts for each child in each subject
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

Run the setup script. It asks for your chosen admin password:

```bash
bash installation.sh
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
- **View child progress**: practice history, per-word performance stats, awards, score chart
- **See progress charts**: **Progress overview** (`/admin/progress`) lists every child, with links to Spelling and Times tables charts. Each chart page shows accuracy and mastery over time. A practice is charted only when it has at least 10 ordinary first attempts. You can open the evidence for one practice, and the history of one word or fact
- **Unlock lists and games manually**: grant a child access to any list or reward game at any time
- **Warm the audio cache**: pre-generate audio for all words so children don't experience delays mid-practice

### Children

Children log in with their name and password. From their dashboard they can:

- Start a spelling practice or a times tables practice. The app chooses the items, so there is no list to pick
- See how many words they have tried in each list
- See recent practice scores, and their badges, medals, and trophies
- Play the mini games they have earned

### Spelling practice flow

1. A word is read aloud — the child can click **Play Word** to hear it again
2. For words with homophones, a **Hear it in a sentence** button is also shown; clicking it plays a sentence using the word in context
3. The child types their spelling and submits
4. If correct, a "Well done!" message appears on the next word
5. If wrong, the word is shown on screen; the child clicks **I'm Ready — Hide Word**, can click **Hear the word again**, then types it again (worth 1 point instead of 2)
6. After 10 words, a child who scored under 20 may answer extra words, one at a time, for +1 point each
7. Results are shown with a full breakdown
8. Scoring 10/20 or higher earns one play of a mini game

### Times tables practice flow

1. A question such as `3 × 4` or `12 ÷ 3` is shown, and the child types the number
2. If correct, a "Well done!" message appears on the next question
3. If wrong, a clue is shown and the child tries again for 1 point. A multiplication clue counts up in steps. A division clue is a picture of counters in equal groups
4. If wrong again, the completed fact is shown kindly and the practice moves on
5. After 10 questions the child can top up, then sees results. Scoring 10/20 or higher earns one play of a mini game

The app also records how long each answer takes. Only the admin sees this.

## Scoring and progression

| Result | Points |
|---|---|
| Correct on first attempt | 2 |
| Correct on second attempt | 1 |
| Wrong on both attempts | 0 |
| **Maximum per test** | **20** |

### Which words are practised

Each spelling practice is ten words: one **focus word** (the next new word in curriculum
order, kept in every practice until it is spelled right first try three times in a row),
five of the weakest words, and four mastered words that have gone longest without
practice. When no new word is left to introduce, a practice is six weak and four
mastered words. A new child's first practice is ten new words. A word is **mastered**
when the child's latest three first attempts at it were all correct. Only first attempts
count as evidence. Lists and words follow an explicit curriculum order. The next list
opens when every word in the child's lists has been introduced. See
`services/spelling_progression.py`.

### Which times tables are practised

Factors run from 2 to 12. There is no ×0, ÷0, ×1 or ÷1. Each fact family (for example
3 × 4, 4 × 3, 12 ÷ 3, 12 ÷ 4) is introduced together. Tables open in this order: 2 and 10,
5, 4, 3, 6, 8, 9, 7, 11, 12. The next table opens when every question in the latest one is
secure (the latest three first attempts correct). A practice holds the family being
introduced, the weakest questions, and the questions practised longest ago. See
`services/arithmetic_progression.py`.

### Badges, medals, and trophies

| Award | Condition | Frequency |
|---|---|---|
| ⭐ Badge | Final score ≥ 16/20, in either subject | At most one per child per Europe/London day |
| 🏅 Medal | Ten more distinct items first mastered (10, 20, 30 ...) | An item counts once, ever |
| 🏆 Trophy | Every word in a list, or every question of a times table (2 to 12), mastered at least once | Once per list or table, permanent. Unwon trophies show as grey outlines in the cabinet |

Starting a new list or table shows a plain "You've started ..." message with no trophy. Only every third badge unlocks a reward game. Medals and trophies do not.

### Mini games

- A practice scoring 10/20 or higher earns one game play. A lower score forfeits an unspent one. The credit is stored on the server.
- Play time is 60 seconds at 10/20, plus 6 seconds per extra point, up to 120 seconds.
- The games played in the last 30 days are listed first. The rest are under **All games**.
- A game file is sent to a child only through a single-use launch link that lasts 5 minutes.
- Classic games are always available. Reward games unlock with every third badge.

## Project structure

```
spelling_app/
├── main.py                  # App factory, middleware, login/logout routes, game file route
├── database.py              # Schema, get_db(), init_db(), additive migrations
├── auth.py                  # Password hashing, session guards, CSRF
├── templates_env.py         # Shared Jinja2 instance, colour palettes, game list, static_version helper
├── routers/
│   ├── admin.py             # /admin/*: word lists, children, game unlocks
│   ├── admin_progress.py    # /admin/progress and per-child progress pages
│   ├── arithmetic.py        # /arithmetic/*: times tables practice
│   ├── child.py             # /child/*: dashboard, game wrapper
│   └── spelling.py          # /test/*: spelling practice
├── services/
│   ├── tts.py                    # gTTS audio generation with file caching
│   ├── spelling_progression.py   # Per-word selection and list unlocking
│   ├── progression_backfill.py   # One-time backfill of medals and trophies
│   ├── arithmetic_facts.py       # Facts, families, table order, clues
│   ├── arithmetic_progression.py # Per-question selection and table unlocking
│   ├── gamification.py           # Badge, medal, and trophy rules
│   ├── game_rewards.py           # Reward-game unlocks (every third badge)
│   ├── game_activity.py          # Game credits, plays, launch links, recent games
│   └── progress_monitoring.py    # Read-only queries for the admin progress pages
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
│   └── admin/               # dashboard, child_detail, edit_child, word_lists, edit_word_list, progress_*
├── tests/                   # pytest suite
└── mini_games/              # Standalone HTML canvas games (served by a route)
```

## Security

- All passwords hashed with bcrypt
- Session cookies are signed (`SessionMiddleware` with a secret key)
- CSRF tokens on every POST form
- Game credits live in the database, not in the session cookie, so a copied cookie cannot earn or spend a play
- Child accounts get game files only through single-use launch links
- Progress pages need the admin login
- All SQL queries use parameterised statements
- TTS filenames sanitised with a regex allowlist before writing to disk
- Set `HTTPS_ONLY=true` in `.env` for production deployments

## Deployment

See `SETUP.md` for how the live app and the staging copy are deployed. Anything pushed to `main` goes live within 60 seconds.

## License

MIT

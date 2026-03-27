# Spelling App — Implementation Plan

## Context
Building a web-based spelling practice app for primary-school children. FastAPI + SQLite backend, Jinja2 + vanilla JS frontend, Google TTS with local caching for audio. Internet-hosted. The goal is a secure, engaging app with adaptive word selection, gamification (badges/trophies), daily colour palette rotation, and mini game rewards.

---

## Open Questions (resolve before/during Phase 1–2)

1. **Word uniqueness**: Can the same word appear in two different lists (e.g. "because" in Year 1 and a custom list)? The plan below uses a surrogate int PK on `words` with a `UNIQUE(word, list_id)` constraint, which allows this. If same word must be unique globally, change `word` to be the sole PK.
2. **Visual mode timing**: How long should a word be shown before hiding in visual mode? Suggest 3 seconds as default — should it be configurable per child in the admin interface?
3. **TTS voice**: Using `en-GB-Standard-A` (British female voice) — OK?
4. **Mini game unlock condition**: Is a mini game reward shown after *any* completed session on an unmastered list, or only if the child scored above some threshold?

---

## Tech Stack
- **Backend**: FastAPI + `sqlite3` (raw prepared statements, no ORM)
- **Frontend**: Jinja2 templates + vanilla JS (no build step)
- **Audio**: Google Cloud TTS (`google-cloud-texttospeech`) with file caching in `static/audio/`
- **Charts**: Chart.js via CDN (single `<script>` tag in `base.html`)
- **Sessions**: Starlette `SessionMiddleware` (signed cookies, `https_only=True`)
- **Passwords**: `bcrypt`

### dependencies (requirements.txt)
```
fastapi
uvicorn[standard]
jinja2
python-multipart
itsdangerous
bcrypt
python-dotenv
google-cloud-texttospeech
```

---

## Database Schema

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    dob           TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    date_created  TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    mode          TEXT NOT NULL DEFAULT 'audio'  -- 'audio' or 'visual'
);

CREATE TABLE word_lists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    year_group INTEGER            -- NULL for custom lists
);

CREATE TABLE words (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    word    TEXT NOT NULL,
    list_id INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    UNIQUE(word, list_id)
);

CREATE TABLE test_sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id   INTEGER NOT NULL REFERENCES word_lists(id),
    score     INTEGER NOT NULL,
    max_score INTEGER NOT NULL  -- always 20 (10 words × 2 pts)
);

CREATE TABLE spelling_attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id        INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    correct        INTEGER NOT NULL,   -- 0 or 1
    attempt_number INTEGER NOT NULL,   -- 1 or 2
    session_id     INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE
);

CREATE TABLE user_list_unlocks (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id     INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    unlocked_at TEXT NOT NULL,
    PRIMARY KEY (user_id, list_id)
);

CREATE TABLE user_badges (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id    INTEGER NOT NULL REFERENCES word_lists(id) ON DELETE CASCADE,
    badge_type TEXT NOT NULL,   -- 'badge' or 'trophy'
    earned_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, list_id, badge_type)
);

CREATE TABLE audio_cache (
    word_text  TEXT PRIMARY KEY,   -- keyed on lowercase word text, shared across lists
    file_path  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

Key decisions:
- Junction tables (`user_list_unlocks`, `user_badges`) instead of bool columns — no schema changes needed when new lists are added.
- Admin is NOT stored in `users`; credentials live in `.env` only.
- `audio_cache` keyed on word text (not word_id) so the same word in two lists shares one audio file.

---

## Project Structure

```
spelling_app/
├── .env                        # SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD_HASH, GOOGLE_CREDENTIALS_PATH
├── main.py                     # App factory, middleware, StaticFiles mounts, startup event, login/logout
├── database.py                 # get_db(), init_db() with all CREATE TABLE statements, PRAGMA setup
├── auth.py                     # hash_password(), verify_password(), get_current_user(), require_child(), require_admin(), csrf utils
├── routers/
│   ├── admin.py                # /admin/* — word lists, words, child profiles, per-child dashboard
│   ├── child.py                # /child/* — dashboard, pick-list
│   └── spelling.py             # /test/* — start, word, results
├── services/
│   ├── tts.py                  # get_audio_url(word_text, db) — calls Google TTS then caches
│   ├── word_selection.py       # select_words(user_id, list_id, n, db) — weighted random sampling
│   └── gamification.py         # check_and_award(user_id, list_id, db) — badges, trophies, list unlocking
├── seed/
│   └── curriculum_words.py     # UK National Curriculum Years 1–6 word lists; idempotent seed(db)
├── static/
│   ├── css/style.css           # All colours via var(--color-1)..var(--color-5)
│   ├── js/spelling.js          # Test flow: audio playback, visual timer, "I'm Ready" flow, submit guard
│   └── audio/                  # Cached .mp3 files (git-ignored)
├── templates/
│   ├── base.html               # Palette injection, Chart.js CDN, palette shuffle JS
│   ├── login.html
│   ├── child/
│   │   ├── dashboard.html
│   │   ├── pick_list.html
│   │   ├── test.html           # Two-attempt test UI (rendered differently per attempt/mode)
│   │   ├── results.html
│   │   └── game_reward.html
│   └── admin/
│       ├── dashboard.html
│       ├── child_detail.html   # Test history, per-word stats, badge progress, Chart.js chart
│       ├── word_lists.html
│       ├── edit_child.html
│       └── edit_word_list.html
└── mini_games/                 # Existing standalone HTML canvas files (served as StaticFiles)
```

---

## Implementation Phases

### Phase 1: Foundation — DB, Auth, Routing
- `database.py`: `get_db()` context manager, WAL mode + FK enforcement at open, `init_db()` with all CREATE TABLE statements.
- `auth.py`: `hash_password()`, `verify_password()`, `get_current_user()`, `require_child()`, `require_admin()`. Simple CSRF token utility (generate on GET, verify on POST, ~20 lines).
- `main.py`: FastAPI app, `SessionMiddleware` (`https_only=True`, `same_site="lax"`), `StaticFiles` mounts for `/static` and `/mini-games`, router includes, startup event calling `init_db()` then `seed()`.
- Login/logout routes on `main.py`. Admin auth checks against `.env` credentials (not DB). On success, write `{"user_id": ..., "is_admin": ...}` to session.
- **Verify**: login works for admin and child; unauthenticated access to protected routes redirects to `/login`.

### Phase 2: Admin Interface
- Word list CRUD: list all, create, edit (name/year_group), delete (cascades to words + audio cache files), add/remove individual words.
- Child management: create (name, DOB, password, mode, initial unlocked lists), edit, reset password, manually unlock lists, delete.
- `admin/child_detail.html`: test session history table, per-word performance table, badge/trophy status, Chart.js score-over-time chart.
- **Verify**: full CRUD cycle for word lists and children.

### Phase 3: Spelling Test Core Flow
Session state (stored in signed cookie — 10 int IDs is ~50 bytes, well under 4KB limit):
```
test_session_id, word_queue: list[int], current_index: int, attempt_number: int
```

Route flow:
1. `GET /test/start/{list_id}` — verify child has list unlocked → call `select_words()` → create `test_sessions` row → write state to session → redirect to `/test/word`.
2. `GET /test/word` — if `current_index >= 10` redirect to results; else render `test.html` with current word. **Critical**: on attempt 1, correct spelling must NOT be in page source. On attempt 2, include it.
3. `POST /test/word` — compare answer case-insensitively. Record `spelling_attempts`. Score: correct attempt 1 → 2pts, correct attempt 2 → 1pt, wrong attempt 2 → 0pts. Update `test_sessions.score`. Advance or set `attempt_number=2` as appropriate. Redirect back to `GET /test/word`.
4. `GET /test/results` — query completed session + all attempts. Call `gamification.check_and_award()`. Render results.

`test.html` UI states:
- **Audio mode, attempt 1**: "Play Word" button (no autoplay — browsers block it), text input, submit.
- **Visual mode, attempt 1**: word shown → JS countdown timer → word hidden → input enabled.
- **Attempt 2 (both modes)**: correct spelling shown prominently → "I'm Ready" button → JS hides spelling, reveals input.

`static/js/spelling.js` reads config from `data-*` attributes on a `<div id="test-root">` element — no inline scripts in templates.

- **Verify**: full 10-word session completes correctly; two-attempt scoring is accurate; correct spelling not visible in page source on attempt 1.

### Phase 4: Word Selection Algorithm
`services/word_selection.py` — `select_words(user_id, list_id, n, db)`:
1. Fetch all word IDs for the list.
2. For each word, compute average score per session using:
   ```sql
   SELECT session_id,
          MAX(CASE WHEN attempt_number=1 AND correct=1 THEN 2
                   WHEN attempt_number=2 AND correct=1 THEN 1 ELSE 0 END) AS word_score
   FROM spelling_attempts WHERE user_id=? AND word_id=? GROUP BY session_id
   ```
   Then average `word_score` across sessions. Words with no history → weight = 2.
3. Weight = `1 / (avg_score + 0.5)`.
4. Use Efraimidis-Spirakis weighted sampling without replacement: sort by `random.random() ** (1/weight)`, take top N. No external dependencies.
5. If list has fewer than N words, return all shuffled.

### Phase 5: Gamification
`services/gamification.py` — `check_and_award(user_id, list_id, db)`:
- **Badge**: avg score across all word/session pairs for this list ≥ 1.4 (70% of max 2.0) → insert `user_badges` with `badge_type='badge'`.
- **Trophy**: every word in list has at least one `spelling_attempts` row with `attempt_number=1 AND correct=1` → insert `badge_type='trophy'`.
- **List unlock**: on badge award, find list with `year_group = current + 1` (or +2 for Year 1→3, Year 3→5 curriculum gaps). Insert into `user_list_unlocks` if not present.
- Returns `{"badge_awarded": bool, "trophy_awarded": bool, "lists_unlocked": [int]}` — used by results route to show congratulations.

Mini game reward: in results route, if no badge yet on this list and this is any completed session → set session flag. Results page shows a "You've unlocked a game!" section linking to a randomly chosen game from `mini_games/`.

### Phase 6: Colour Palettes
- 7 palettes defined as a constant list in `main.py`. Inject into all templates via a Jinja2 global: `templates.env.globals["current_palette"] = lambda: PALETTES[datetime.today().weekday()]`.
- `base.html`: emit `const palette = {{ current_palette().colours | tojson }};` and a Fisher-Yates shuffle that sets `--color-1` through `--color-5` CSS variables. Shuffle runs on every page load.
- `style.css`: all colour references use `var(--color-N)`.

### Phase 7: Google TTS Caching
`services/tts.py` — `get_audio_url(word_text, db)`:
1. Sanitise: `filename = re.sub(r'[^a-z0-9]', '_', word_text.lower()) + '.mp3'`.
2. Query `audio_cache` by `word_text`. If found, return stored URL.
3. If not found: call `texttospeech.TextToSpeechClient`, voice `en-GB-Standard-A`, encoding `MP3`. Write bytes to `static/audio/{filename}`. Insert into `audio_cache`. Return `/static/audio/{filename}`.
4. On API failure: log error, return `None`. Template shows "word unavailable" fallback.

Admin endpoint `POST /admin/warm-audio-cache`: iterates all words, pre-generates missing audio. Run once after initial DB seed.

### Phase 8: Mini Games Integration
- `StaticFiles` mount at `/mini-games` serves the 7 existing HTML files directly — no modifications needed.
- `MINI_GAMES` list in `main.py` maps filenames to friendly names/descriptions.
- Child dashboard shows a "Games" section; games accessible once any has been unlocked (or always — decide per preference).
- Results page shows a reward link when applicable.

### Phase 9: Child Dashboard
`routers/child.py`:
- `GET /child/dashboard`: unlocked lists with badge/trophy status, last 5 sessions, total score summary.
- `GET /child/pick-list`: cards for each unlocked list with badge/trophy icons and "Start Test" button.

`child/dashboard.html`: greeting, badge wall grid, recent scores Chart.js chart, games section, "Start a Test" button.

---

## Security Checklist
- `SessionMiddleware`: `https_only=True`, `same_site="lax"`, `secret_key` from env var.
- Every `POST` route verifies CSRF token.
- Every admin route declares `Depends(require_admin)` — never rely on template-level hiding.
- All SQL queries use `?` placeholders — never f-strings with user data.
- TTS filenames sanitised with regex allow-list before `os.path.join`.
- `.env` and `static/audio/` in `.gitignore`.
- `bcrypt` for all passwords (admin hash generated once via CLI: `python -c "import bcrypt; print(bcrypt.hashpw(b'pw', bcrypt.gensalt()).decode())"`).

---

## Pitfalls to Watch
- **Audio autoplay**: browsers block autoplay without user gesture — use an explicit "Play Word" button, not `audio.autoplay`.
- **Correct spelling in source**: on attempt 1, the word must not appear anywhere in the HTML source. Pass it to the template only when `attempt_number == 2`.
- **Word selection edge case**: if list has ≤10 words, return all shuffled (no duplicates).
- **UK curriculum year grouping**: the statutory lists are Year 1–2 and Year 3–4 and Year 5–6 (pairs, not individual years). Seed accordingly with `year_group` = 1, 3, 5.
- **Google TTS latency**: warm the cache via the admin endpoint after seeding — don't let a child encounter a 1–2s API call mid-test.

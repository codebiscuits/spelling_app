# Setup & Getting Started

## 1. Install dependencies

```bash
uv sync
```

## 2. Create your `.env` file

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
SECRET_KEY=<random string>
ADMIN_USERNAME=<your chosen admin username>
ADMIN_PASSWORD_HASH=<bcrypt hash of your admin password>
HTTPS_ONLY=false
```

**Generating a secret key:**
```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

**Generating the admin password hash:**
```bash
uv run python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```
Replace `yourpassword` with your actual admin password. Paste the output into `.env` as `ADMIN_PASSWORD_HASH`.

---

## 3. Start the server

```bash
uv run uvicorn main:app --reload
```

The app will be available at [http://localhost:8000](http://localhost:8000).

On first startup the database is created automatically and seeded with the UK National Curriculum word lists for Years 1–2, 3–4, and 5–6.

---

## 4. Log in as admin

Go to [http://localhost:8000/login](http://localhost:8000/login) and log in with the `ADMIN_USERNAME` and password you set in `.env`.

---

## 5. Add a child

1. From the admin dashboard, click **Add Child**
2. Fill in:
   - **Name** — this is what the child uses to log in (e.g. `Emma`)
   - **Date of Birth**
   - **Password** — a simple password the child will remember
   - **Unlocked Word Lists** — tick the lists this child should have access to (start with Year 1–2)
3. Click **Create**

---

## 6. Child logs in

The child goes to the login page and enters:
- **Name** — exactly as entered by the admin (case-sensitive)
- **Password**

They are taken straight to their dashboard.

---

## 7. Taking a spelling test

1. From their dashboard (or the **Start Test** button), the child clicks **Choose a Word List**
2. They pick a list and the test begins — 10 words per test
3. For each word:
   - Click **Play Word** to hear it, then type the spelling
   - If wrong on the first attempt, the word is shown on screen; click **I'm Ready — Hide Word** then type it again (worth 1 point instead of 2)
5. After 10 words the results page shows the score, any badges or trophies earned, and — if the score was 16/20 or higher — a mini game to play as a reward

---

## 8. Badges, medals, and trophies

Awards are calculated automatically after each test:

| Award | Condition |
|-------|-----------|
| **Badge** ⭐ | Session score ≥ 16/20 (awarded every qualifying test) |
| **Medal** 🏅 | ≥ 50% of the list's words spelled correctly first-try (cumulative, once per list) |
| **Trophy** 🏆 | ≥ 95% first-try correct + all remaining words second-try correct (cumulative, once per list) |

Earning a **trophy** also **unlocks the next year group's lists** automatically:
- Year 1–2 trophy → unlocks Year 3–4
- Year 3–4 trophy → unlocks Year 5–6

---

## 9. Managing word lists

Go to **Admin → Word Lists** to:
- Create custom lists with any name and optional year group
- Add or remove individual words
- Delete lists (this removes all associated progress)

Custom lists must be unlocked manually for each child via **Edit Child → Unlocked Word Lists**.

---

## 10. Viewing a child's progress

From the admin dashboard, click a child's name to see:
- A score chart across recent sessions
- Which badges and trophies they have earned
- Per-word performance (how many sessions, how often spelled correctly first try)
- Quick unlock button to give access to additional lists

---

## Audio files

Audio is generated on demand the first time a word is tested and cached to `static/audio/`. This requires an internet connection. You can pre-generate audio for all words in all lists via **Admin Dashboard → Warm Audio Cache**.

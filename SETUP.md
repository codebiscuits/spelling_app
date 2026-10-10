# Setup & Getting Started

## 1. Installation

The easiest way is to run the setup script:

```bash
bash installation.sh
```

It will prompt you for an admin password, then generate `.env` automatically with a random secret key, bcrypt-hashed password, and restricted file permissions (`chmod 600`).

**Manual alternative:** install python dependencies and then copy the .env.example and fill in the values yourself:

```bash
uv sync
cp .env.example .env
```

```
SECRET_KEY=<random string>
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<bcrypt hash of your admin password>
HTTPS_ONLY=false
```

Generating a secret key:
```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

Generating the admin password hash:
```bash
uv run python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

---

## 2. Start the server

```bash
uv run uvicorn main:app --reload
```

The app will be available at [http://localhost:8000](http://localhost:8000).

On first startup the database is created automatically and seeded with the UK National Curriculum word lists for Years 1–2, 3–4, and 5–6.

---

## 3. Log in as admin

Go to [http://localhost:8000/login](http://localhost:8000/login) and log in with the `ADMIN_USERNAME` and password you set in `.env`.

---

## 4. Add a child

1. From the admin dashboard, click **Add Child**
2. Fill in:
   - **Name** — this is what the child uses to log in (e.g. `Emma`)
   - **Date of Birth**
   - **Password** — a simple password the child will remember
   - **Unlocked Word Lists** — tick the lists this child should have access to (start with Year 1–2)
3. Click **Create**

---

## 5. Child logs in

The child goes to the login page and enters:
- **Name** — exactly as entered by the admin (case-sensitive)
- **Password**

They are taken straight to their dashboard.

---

## 6. Taking a spelling practice

1. From their dashboard, the child clicks **Start a spelling practice**. The app chooses the words, so there is no list to pick. A practice is 10 words
2. For each word:
   - Click **Play Word** to hear it, then type the spelling
   - For words that have homophones (e.g. *eight*, *reign*, *where*), a **Hear it in a sentence** button also appears. It plays a sentence using the word in context
   - If wrong on the first attempt, the word is shown on screen. Click **I'm Ready — Hide Word**, then type it again (worth 1 point instead of 2). The **Hear the word again** button plays the word
3. A ten-segment bar at the top shows how far through the practice the child is
4. After 10 words, a child who scored under 20 may answer extra words, one at a time, for +1 point each
5. The results page shows the score and any badges, medals, or trophies earned. If the score was 10/20 or higher, the child can play one mini game as a reward

Which words appear is decided by the app. Each practice has one new word (the next in curriculum order), five of the child's weakest words, and four mastered words that have gone longest without practice. A word is mastered when the latest three first attempts at it were correct.

## 6b. Taking a times tables practice

1. From their dashboard, the child clicks **Start a times tables practice**. A practice is 10 questions, such as `3 × 4` or `12 ÷ 3`
2. The child types the number. If wrong, a clue is shown and the child tries once more for 1 point. A division clue is a picture of counters in equal groups
3. If the second try is wrong too, the completed fact is shown and the practice moves on
4. Top-ups and results work as they do for spelling, and the same 10/20 rule earns a mini game

Factors run from 2 to 12. Tables open in this order: 2 and 10, 5, 4, 3, 6, 8, 9, 7, 11, 12. The next table opens when every question in the latest one is secure (the latest three first attempts correct).

---

## 7. Badges, medals, trophies, and games

Awards are calculated automatically after each practice, in either subject:

| Award | Condition |
|-------|-----------|
| **Badge** ⭐ | Final score ≥ 16/20, at most one per child per Europe/London day |
| **Medal** 🏅 | Every ten distinct items first mastered (words, or times-tables questions) |
| **Trophy** 🏆 | The first practice attempt at a word from a list the child has not started, or at a question on a new table |

Only every third badge unlocks a reward game. Medals and trophies do not.

Games work like this:

- A practice scoring **10/20 or higher** earns one game play. The play is stored on the server. A later practice scoring under 10 forfeits an unspent play
- Play time is 60 seconds at 10/20, plus 6 seconds per extra point, up to 120 seconds
- The games a child played in the last 30 days are listed first. The rest are under **All games**
- Classic games are always available. Reward games appear once unlocked. You can also unlock a reward game by hand in the **Reward Games** section of the child's admin page

The next word list opens automatically when a child has been introduced to every word in the lists they have.

---

## 8. Managing word lists

Go to **Admin → Word Lists** to:
- Create custom lists with any name and optional year group
- Add or remove individual words
- Delete lists (this removes all associated progress)

Custom lists must be unlocked manually for each child via **Edit Child → Unlocked Word Lists**.

---

## 9. Viewing a child's progress

From the admin dashboard, click a child's name to see:
- A score chart across recent sessions
- Which badges, medals, and trophies they have earned
- Per-word performance (how many sessions, how often spelled correctly first try)
- Quick unlock button to give access to additional lists

For charts over time, click **Progress overview** on the admin dashboard (`/admin/progress`). It lists every child, with a **Charts** column that links to:

- `/admin/children/{id}/spelling` and `/admin/children/{id}/arithmetic`: Chart.js charts of first-try accuracy, items mastered or secure, and (times tables) median answer time
- One page per practice, showing each question, the first and second attempts, and the top-ups
- One page per word or fact, showing its latest first attempts and its status

A practice is charted only when it has at least 10 ordinary first attempts (first tries, not second tries or top-ups). Shorter practices appear in the history list but not on the charts. These pages only read data. They never change it.

---

## Audio files

Audio is generated on demand the first time a word is tested and cached to `static/audio/`. This requires an internet connection. You can pre-generate audio for all words in all lists via **Admin Dashboard → Warm Audio Cache**.

---

## Deployment and staging

**Anything pushed to `main` goes live to children within 60 seconds.** Test on staging first, and never push to `main` by accident.

### Live

- The live app runs on the fileserver as the system service `spelling-app`, on port 8000
- The user timer `spelling-app-update.timer` runs `scripts/update.sh` in the fileserver checkout (`~/Apps/spelling_app`) every minute
- If `origin/main` has new commits, the script runs `git pull origin main` and `uv sync --no-dev`, then restarts `spelling-app`. If nothing changed, it does nothing
- `scripts/update.sh` is part of the fileserver checkout and is not tracked in this repo

### Staging

- Staging is a second checkout at `~/Apps/spelling_app_staging` on the fileserver, on branch `staging`
- It runs on port 8010 on the Tailscale address, with its own database, `staging.db`. This is a copy of the newest nightly snapshot, so it holds real data but is separate from the live database
- To deploy a branch to staging, run these from your development clone:

```bash
git push -f staging <branch>:staging
ssh fileserver ~/machine-setup/fileserver/spelling-staging.sh restart
```

- To reload the staging data from the newest nightly snapshot:

```bash
ssh fileserver ~/machine-setup/fileserver/spelling-staging.sh refresh-db
```

- The scripts that install staging and protect the live folder are in the separate machine-setup repo (`fileserver/deploy-spelling-staging.sh`), not in this repo. See that repo's `fileserver/README.md` for how staging is set up

### Before each go-live

1. Take a database snapshot on the fileserver:

```bash
systemctl --user start app-db-backup.service
```

2. Check the change on staging
3. Only then merge to `main` and push

Database migrations in `database.py` are additive only: new tables and columns, and data written into them. They never change or drop an existing column. Reverting the code therefore needs no database restore.

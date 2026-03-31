---
name: Project tech stack
description: Confirmed tech stack for the spelling app
type: project
---

FastAPI + SQLite (raw SQL, no ORM) backend, Jinja2 + vanilla JS frontend, gTTS for audio (British accent, no API key), bcrypt for passwords, Starlette SessionMiddleware for signed-cookie sessions, Chart.js via CDN for graphs. Package management is uv.

**Why:** Chosen for simplicity — no build tooling, no credentials needed for audio, no ORM complexity.

**How to apply:** Don't suggest ORMs, build tools, or cloud TTS. Keep dependencies minimal.

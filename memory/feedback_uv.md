---
name: Use uv for Python package management
description: User manages Python dependencies with uv, not pip
type: feedback
---

Always use `uv run` or `uv` commands instead of `pip` or bare `python`/`python3`.

**Why:** User has set up the project with uv.

**How to apply:** Use `uv run python ...` to run scripts, `uv add` to add packages, never `pip install`.

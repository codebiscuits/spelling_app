# Memory Index

- [Use uv for Python package management](feedback_uv.md) — Always use `uv run`/`uv add`, never `pip install`
- [Project tech stack](project_stack.md) — FastAPI, SQLite, gTTS, bcrypt, Jinja2, vanilla JS, uv
- [Shared Jinja2 templates instance](feedback_shared_templates.md) — Import `templates` from `templates_env.py`; never create a new instance
- [Starlette TemplateResponse new API](feedback_template_response_api.md) — `request` is positional arg, not in context dict
- [Gamification mechanics](project_gamification.md) — Badge (≥16/20), Medal (50% first-try), Trophy (95% first-try + unlock)

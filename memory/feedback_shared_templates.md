---
name: Shared Jinja2 templates instance
description: All routers must import templates from templates_env.py — never create a new Jinja2Templates instance
type: feedback
---

Always import `templates` from `templates_env.py`. Never instantiate `Jinja2Templates` inside a router or any other module.

**Why:** Jinja2 globals (e.g. `current_palette`) are set on the shared instance. A new instance won't have those globals, causing TemplateNotFound or undefined variable errors.

**How to apply:** Any time a router or service needs to render a template, use `from templates_env import templates`.

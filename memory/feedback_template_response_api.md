---
name: Starlette TemplateResponse new API
description: Use new-style TemplateResponse with request as positional arg, not in context dict
type: feedback
---

Always call `templates.TemplateResponse(request, "name.html", context)` — `request` is the first positional argument, NOT a key in the context dict.

**Why:** Old-style API `TemplateResponse("name.html", {"request": request, ...})` causes a Jinja2 LRU cache TypeError (unhashable dict) in newer Starlette versions.

**How to apply:** Every `TemplateResponse` call in every router must follow this pattern.

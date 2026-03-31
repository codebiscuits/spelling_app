---
name: Gamification mechanics
description: Badge/medal/trophy award conditions and list unlock logic
type: project
---

Three award types, evaluated in `services/gamification.py` after every test:

- **Badge** ⭐ — session score ≥ 16/20. Stored in `test_badges` table (unlimited, one per qualifying session).
- **Medal** 🏅 — ≥ 50% of the list's words spelled correctly first-try at least once (cumulative across all sessions). Stored in `user_badges` with `badge_type='medal'`. Once per list.
- **Trophy** 🏆 — ≥ 95% first-try correct + all remaining words second-try correct (cumulative). Stored in `user_badges` with `badge_type='trophy'`. Once per list. Also triggers automatic unlock of the next year group's lists.

Year group unlock progression: Y1 → Y3 (next_yg = current + 2 for Y1/Y3), otherwise current + 1.

**Why:** Designed to give frequent positive reinforcement (badges) while making medals and trophies meaningful milestones.

**How to apply:** Don't conflate badge/medal/trophy — they are distinct award types with separate tables/columns.

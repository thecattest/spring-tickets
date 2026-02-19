# Milestones

## v0.1 — VK Bot MVP (Complete)

**Completed:** 2026-02-18
**Phases:** 0-5 (Phase 6 deferred)

**Delivered:**
- Database layer with atomic seat occupancy (SeatAssignment partial index)
- VK bot with full reservation lifecycle: create → add seats → pay → cancel
- Admin reserve management (/reserve)
- Debtors tracking (/debtors) + cron reminders
- Web hall map + payments dashboard

**Phase count:** 6 phases (0-5), 13 plans executed

---

## v0.2 — Рефакторинг архитектуры бота (Active)

**Started:** 2026-02-19
**Status:** Defining requirements

**Goal:** Eliminate ~335+ lines of handler duplication, extract reusable abstractions (constants, router, steps, texts), improve navigation UX (/cancel → back, /exit → IDLE).

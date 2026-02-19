---
phase: 10-router
plan: 02
subsystem: infra
tags: [vkbottle, router, fsm, handler-registration, labeler]

# Dependency graph
requires:
  - phase: 10-01
    provides: Router class with BotLabeler, register_all(), and storage injection via _wrap()
provides:
  - bot/main.py wired to Router — single entry point for all 24 handler registrations
  - bot.labeler.load(router.labeler) transferring all handlers to the bot in enforced order
  - Zero register_handlers() calls remaining in main.py
affects: [11-migration, 12-cancel]

# Tech tracking
tech-stack:
  added: []
  patterns: [Router-based handler registration activated in bot startup path]

key-files:
  created: []
  modified: [bot/main.py]

key-decisions:
  - "router = Router(storage=redis_storage) uses the RedisStorage instance directly — clearer than bot.state_dispenser"
  - "BaseStateGroup import removed — was unused in main.py after handler module imports removed"

patterns-established:
  - "Bot startup order: config → Redis → Bot → Router.register_all() → labeler.load() → DB → Layout → poll"

# Metrics
duration: 1min
completed: 2026-02-19
---

# Phase 10 Plan 02: Router Wiring Summary

**bot/main.py replaces 7 register_handlers() calls + bulk handler import with Router(storage=redis_storage).register_all() + bot.labeler.load(router.labeler), activating central handler registration and enforced dispatch order**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-02-19T19:01:39Z
- **Completed:** 2026-02-19T19:02:23Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- bot/main.py now uses Router for all handler registration — zero scattered register_handlers() calls
- Enforced dispatch order (forwarded → commands → states) now active at bot startup
- Bulk handler module import removed from main.py — handlers are lazy-loaded inside Router
- Unused BaseStateGroup import cleaned up

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace register_handlers() calls with Router in bot/main.py** - `cb7c076` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `bot/main.py` - Replaced 7 register_handlers() calls with Router(storage=redis_storage).register_all() + bot.labeler.load(router.labeler); removed bulk handler import and unused BaseStateGroup

## Decisions Made
- `Router(storage=redis_storage)` uses the local `redis_storage` variable directly rather than `bot.state_dispenser` — both reference the same object but using `redis_storage` makes the dependency explicit and avoids implying the bot must exist first.
- `BaseStateGroup` import removed — it was imported at the top of main.py but never referenced directly in any function body.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Router is fully wired — all 24 handlers registered via central Router at bot startup
- Phase 10 complete: RTR-01 (auto-registration), RTR-02 (universal commands), RTR-03 (enforced order) all achieved
- Phase 11 (migration) can now migrate individual handler files to use new FSM config and texts.py constants — each handler file is independently modifiable without touching main.py

---
*Phase: 10-router*
*Completed: 2026-02-19*

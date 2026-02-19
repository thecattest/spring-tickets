---
phase: 11-handler-migration
plan: 07
subsystem: bot
tags: [vkbottle, fsm, handler-migration, texts]

# Dependency graph
requires:
  - phase: 08-foundation
    provides: texts.py with 62 string constants (ERR_*, MSG_*, PROMPT_*)
  - phase: 10-router
    provides: Router._register_commands() already wires debtors handlers via labeler
provides:
  - Migrated debtors.py using texts.* constants, dead code removed
affects:
  - 11-handler-migration (remaining handler files follow same pattern)

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - bot/handlers/debtors.py

key-decisions:
  - "'Обновить' button registration lives in Router._register_commands() (line 184) — not in debtors.py — confirmed correct before removal of register_handlers()"

patterns-established:
  - "Handler-migration pattern: remove register_handlers(), drop Bot import, add 'from bot import texts', replace inline strings with texts.* constants"

# Metrics
duration: 1min
completed: 2026-02-19
---

# Phase 11 Plan 07: Debtors Handler Migration Summary

**`debtors.py` dead `register_handlers()` removed and 3 inline Russian strings replaced with `texts.ERR_NOT_REGISTERED`, `texts.ERR_DB_GET_DEBTORS`, `texts.MSG_NO_DEBTORS`**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-02-19T20:11:03Z
- **Completed:** 2026-02-19T20:12:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Verified "Обновить" button is correctly registered via Router (not via the now-deleted `register_handlers()`)
- Removed 14-line `register_handlers(bot: Bot)` function and unused `Bot` import
- Wired `from bot import texts` and replaced all 3 inline strings with `texts.*` constants
- Both handler signatures (`debtors_command_handler(message)` and `refresh_debtors_handler(message)`) preserved exactly

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove dead code and wire texts.py in debtors.py** - `48494ba` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `bot/handlers/debtors.py` - Removed `register_handlers()`, `Bot` import; added `texts` import; replaced 3 inline strings with `texts.*` constants

## Decisions Made

- "Обновить" button: Confirmed `refresh_debtors_handler` is registered at `bot/router.py:184` via `self.labeler.message(text="Обновить")(refresh_debtors_handler)`. The `register_handlers()` registration of the same handler was pure dead code — safe to remove.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Blocker concern resolved: `debtors.py` read fully before migration; "Обновить" handling confirmed correct via Router before removal of `register_handlers()`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `debtors.py` fully migrated — smallest handler file, simplest pattern (no closures, no steps.py, stateless)
- Remaining Phase 11 handler files: `commands.py`, `reservation.py`, `menu.py`, `deletion.py`, `payment.py`, `reserve.py`
- Pattern is established: remove `register_handlers()`, drop `Bot` import, add `from bot import texts`, wire `texts.*` constants

---
*Phase: 11-handler-migration*
*Completed: 2026-02-19*

---
phase: 11-handler-migration
plan: 05
subsystem: bot
tags: [vkbottle, fsm, menu, constants, texts, StrEnum]

# Dependency graph
requires:
  - phase: 08-foundation
    provides: Btn constants (StrEnum), texts.py message constants
  - phase: 10-router
    provides: Router that registers handlers — register_handlers() now dead
provides:
  - Migrated menu.py with Btn/texts wired, dead code removed
affects: [11-handler-migration, 12-nav]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Btn.ADD/DELETE/DELETE_ALL/PAYMENT/YES/NO for all keyboard button comparisons"
    - "texts.* constants for all user-facing strings in menu handlers"
    - "Lazy import pattern preserved for start_payment_flow to avoid circular import"

key-files:
  created: []
  modified:
    - bot/handlers/menu.py

key-decisions:
  - "else clause preserved as final branch for unknown text in main_menu_handler"
  - "show_main_menu not modified — shared helper called by other handlers, not a state handler"
  - "ERR_DB_LOAD_BOOKING wired in show_main_menu error path (also in scope for texts wiring)"
  - "MSG_CONTINUE_WITH.format(name=...) used for context_switch Btn.NO branch"

patterns-established:
  - "Pattern: if/elif/else with Btn.* constants replaces raw string comparisons"
  - "Pattern: texts.* replaces all inline Russian user-facing strings"

# Metrics
duration: 2min
completed: 2026-02-19
---

# Phase 11 Plan 05: menu.py Migration Summary

**menu.py dead code removed (register_handlers, command dispatch block) and all button comparisons wired to Btn.ADD/DELETE/DELETE_ALL/PAYMENT/YES/NO with texts.* message constants**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-19T20:10:21Z
- **Completed:** 2026-02-19T20:12:03Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Removed `register_handlers()` function with its 2 inner closure wrappers (22 lines gone)
- Removed dead `elif text.startswith("/"):` command dispatch block (18 lines gone)
- Wired `Btn.ADD`, `Btn.DELETE`, `Btn.DELETE_ALL`, `Btn.PAYMENT`, `Btn.YES`, `Btn.NO` for all button comparisons
- Wired `texts.*` constants throughout: `ERR_CONTEXT_LOST`, `PROMPT_ENTER_ROW`, `PROMPT_ENTER_ROW_DELETE`, `ERR_NO_SEATS_TO_DELETE`, `ERR_NO_SEATS`, `ERR_DB_CHECK_SEATS`, `PROMPT_SELECT_ACTION`, `ERR_DB_LOAD_BOOKING`, `ERR_DB_CREATE_BOOKING_SHORT`, `MSG_NEW_BOOKING_NO_RES`, `MSG_NEW_BOOKING_CREATED`, `MSG_CONTINUE_WITH`, `MSG_CANCELLED`
- `show_main_menu` preserved unchanged

## Task Commits

1. **Task 1: Remove dead code and wire Btn/texts in menu.py** - `7be25b0` (feat)

**Plan metadata:** (included in docs commit below)

## Files Created/Modified

- `bot/handlers/menu.py` - Migrated: dead code removed, Btn constants and texts.py wired

## Decisions Made

- `show_main_menu` error path (`ERR_DB_LOAD_BOOKING`) also wired for consistency — it was an inline string matching a texts.py constant and is in scope of texts wiring
- `else:` clause uses `texts.PROMPT_SELECT_ACTION` in both `main_menu_handler` and `context_switch_handler` — same constant, correct reuse

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `menu.py` fully migrated; ready for 11-06 and beyond
- `show_main_menu` shared helper preserved — no breaking changes to callers

---
*Phase: 11-handler-migration*
*Completed: 2026-02-19*

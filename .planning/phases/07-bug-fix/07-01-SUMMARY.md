---
phase: 07-bug-fix
plan: 01
subsystem: bot
tags: [fsm, vkbottle, BotState, enum, state-restoration, context-switch, unit-tests]

# Dependency graph
requires:
  - phase: 02-bot-phase2
    provides: context_switch_handler in bot/handlers/menu.py
provides:
  - BUG-01 fixed: storage.set() now receives BotState enum member, not raw string
  - Unit test suite for BotState string restoration (18 states, 2 formats)
affects:
  - 08-fsm-config
  - 09-router
  - any phase modifying context_switch_handler

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BotState enum restoration: BotState(stored_string.split(':')[-1]) handles both modern and legacy formats"
    - "Unit tests live in tests/ (project-level) alongside bot/tests/ (bot-level)"

key-files:
  created:
    - tests/__init__.py
    - tests/test_bot_state_restoration.py
  modified:
    - bot/handlers/menu.py

key-decisions:
  - "Split on ':' and take [-1] handles both 'BotState:value' (modern) and 'value' (legacy) transparently"
  - "Idle guard checks raw original_state string against 'idle' — works for legacy format; modern 'BotState:idle' passes guard but extracted value is still 'idle', so BotState('idle') == BotState.IDLE"

patterns-established:
  - "FSM state restoration: always convert stored string to enum member before calling storage.set()"

# Metrics
duration: 1min
completed: 2026-02-19
---

# Phase 7 Plan 01: Bug Fix BotState Restoration Summary

**Fixed production bug BUG-01: context_switch_handler now converts stored "BotState:value" string back to BotState enum member before calling storage.set(), unblocking ticketers stuck after pressing "Нет"**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-02-19T15:38:30Z
- **Completed:** 2026-02-19T15:39:55Z
- **Tasks:** 1
- **Files modified:** 3 (1 fix + 2 new test files)

## Accomplishments
- Fixed one-line bug at menu.py:325 — `original_state` string converted to `BotState` enum before `storage.set()`
- Created `tests/test_bot_state_restoration.py` with 3 unit tests covering all 18 BotState values in both modern (`"BotState:value"`) and legacy (`"value"`) string formats
- Confirmed zero regressions against the full test suite (pre-existing failures unrelated to this fix)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix BotState restoration and add unit tests** - `9dad824` (fix)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `bot/handlers/menu.py` - Added `restored_state = BotState(original_state.split(":")[-1])` at line 325; passes `restored_state` to `storage.set()` instead of raw `original_state` string
- `tests/__init__.py` - Empty init to make tests/ a package
- `tests/test_bot_state_restoration.py` - 3 unit tests: modern format restoration, legacy format restoration, idle guard logic

## Decisions Made
- Used `.split(":")[-1]` idiom so a single expression handles both storage formats without branching
- Placed new tests in `tests/` (project root level) rather than `bot/tests/` since this tests cross-cutting FSM behavior, not bot internals

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. Pre-existing test failures in `bot/tests/test_db_integration.py` and `bot/tests/test_redis_fsm.py` were present before this change and are unrelated.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- BUG-01 resolved; ticketers can now decline context switches without getting stuck
- Phase 8 (FSM config) can proceed; the BotState enum is confirmed stable across all 18 values
- No blockers introduced

---
*Phase: 07-bug-fix*
*Completed: 2026-02-19*

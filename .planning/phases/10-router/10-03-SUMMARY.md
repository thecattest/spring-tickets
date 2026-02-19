---
phase: 10-router
plan: 03
subsystem: infra
tags: [vkbottle, router, fsm, commands, exit-handler]

# Dependency graph
requires:
  - phase: 10-01
    provides: Router class with _wrap() and _register_commands()
  - phase: 10-02
    provides: Router wired into bot/main.py
provides:
  - exit_handler in bot/handlers/commands.py — hard reset to IDLE
  - /exit and /Выход registered in router._register_commands() before state handlers
  - RTR-02 gap for /exit is closed
affects: [12-cancel]

# Tech tracking
tech-stack:
  added: []
  patterns: [exit_handler uses same _wrap() pattern as cancel_handler for storage injection]

key-files:
  created: []
  modified: [bot/handlers/commands.py, bot/router.py]

key-decisions:
  - "exit_handler message text is distinct from cancel_handler — enables Phase 12 to differentiate /cancel (back one step) from /exit (hard reset)"
  - "exit_handler NOT added to legacy register_handlers() in commands.py — that function is removed in Phase 11"

patterns-established:
  - "Hard reset pattern: await storage.delete(message.from_id) clears FSM state to IDLE"

# Metrics
duration: ~1 min
completed: 2026-02-19
---

# Phase 10 Plan 03: /exit Command Handler Summary

**exit_handler added to bot/handlers/commands.py with a distinct confirmation message, registered in router._register_commands() via _wrap() for /exit and /Выход, closing the RTR-02 gap identified in 10-VERIFICATION.md**

## Performance

- **Duration:** ~1 min 18 sec
- **Started:** 2026-02-19T19:26:13Z
- **Completed:** 2026-02-19T19:27:31Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- `exit_handler(message, storage)` added to `bot/handlers/commands.py` after `cancel_handler`
- Hard-resets FSM state via `await storage.delete(message.from_id)` — same mechanism as cancel
- Confirmation message "Сессия завершена. Состояние сброшено." is intentionally different from cancel's "Операция отменена." — Phase 12 will use this distinction for /cancel (back one step) vs /exit (hard reset to IDLE)
- `exit_handler` imported and registered in `router._register_commands()` with `_wrap()` for both `/exit` and `/Выход`
- Legacy `register_handlers()` function NOT modified (will be removed in Phase 11)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add exit_handler and register /exit in router** - `5563259` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `bot/handlers/commands.py` — Added `exit_handler(message, storage)` after `cancel_handler`; uses try/except, logs /exit, clears FSM, sends distinct message with commands_keyboard
- `bot/router.py` — Added `exit_handler` to import from bot.handlers.commands; added registration line for `/exit`/`/Выход` after cancel registration

## Decisions Made

- `exit_handler` message text uses "Сессия завершена" rather than "Операция отменена" — the distinction between session termination and operation cancellation is intentional and enables Phase 12 to differentiate the two commands.
- Legacy `register_handlers()` not modified per plan instructions — it will be removed atomically in Phase 11 during handler file migration.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- Gap 1 from 10-VERIFICATION.md (missing /exit handler) is fully closed
- Phase 12 (/cancel back-navigation) can proceed with /exit already in place as the hard-reset anchor
- Phase 11 (handler migration) can remove `register_handlers()` from commands.py without losing /exit functionality

---
*Phase: 10-router*
*Completed: 2026-02-19*

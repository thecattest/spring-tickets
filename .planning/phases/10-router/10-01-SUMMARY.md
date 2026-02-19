---
phase: 10-router
plan: 01
subsystem: bot
tags: [vkbottle, fsm, labeler, router, handler-registration, python]

# Dependency graph
requires:
  - phase: 09-fsm-config-steps
    provides: BotState enum members and FSM storage (RedisStorage) used by Router
  - phase: 08-foundation
    provides: Handler functions in bot/handlers/* that Router registers
provides:
  - Router class in bot/router.py with register_all(), _wrap(), and 3 registration groups
  - Centralized BotLabeler with 24 handlers in enforced dispatch order
  - Storage-injection wrapper pattern via _wrap() replacing 14 ad-hoc closures
affects:
  - 10-02: bot/main.py wiring — router.register_all() and bot.labeler.load(router.labeler)
  - 11-handler-migration: Handlers migrated to new patterns reference Router for registration

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy imports inside registration methods to avoid circular imports with handler files"
    - "_wrap() closure pattern: storage-injecting wrapper instead of per-handler closures"
    - "Enforced dispatch order: forwarded first, commands second, states third"

key-files:
  created:
    - bot/router.py
  modified: []

key-decisions:
  - "Router uses self.labeler (BotLabeler), NOT bot.on — wired to bot in Phase 10-02 via bot.labeler.load()"
  - "start_handler and help_handler registered directly (no wrap) — they only take (message,)"
  - "debtors_command_handler and refresh_debtors_handler registered directly — stateless, no storage needed"
  - "All bot.handlers.* imports are lazy (inside _register_* methods) to prevent circular imports"

patterns-established:
  - "Lazy import pattern: import handlers inside method body, not at module top — prevents circular imports since handlers transitively import from bot.fsm"
  - "_wrap() generates unique __name__ for debug traceability: handler_func.__name__ + '_wrapped'"

# Metrics
duration: 2min
completed: 2026-02-19
---

# Phase 10 Plan 01: Router Class Summary

**Single Router class (bot/router.py) owns a BotLabeler and registers all 24 bot handlers in enforced order: forwarded first, commands second, FSM states third — replacing 7 scattered register_handlers() functions and 14 ad-hoc closures**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-19T18:57:12Z
- **Completed:** 2026-02-19T18:59:17Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Router class created with `register_all()`, `_wrap()`, `_register_forwarded()`, `_register_commands()`, `_register_states()`
- Storage injection centralized via `_wrap()` — no more per-handler closure definitions scattered across files
- Handler dispatch order enforced: forwarded (fwd_messages func rule) -> commands (text rules) -> states (state rules)
- All 24 handler registrations: 1 forwarded + 6 command + 17 state handlers confirmed working

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bot/router.py with Router class** - `b7f66f7` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `bot/router.py` - Router class with 5 methods, 206 lines, lazy handler imports, BotLabeler registration

## Decisions Made
- `from vkbottle.framework.labeler.bot import BotLabeler` used (not `from vkbottle import BotLabeler`) — matches plan's anti-pattern guidance
- `start_handler` and `help_handler` registered without `_wrap()` since they only accept `(message,)` — verified by reading handler signatures
- `debtors_command_handler` and `refresh_debtors_handler` registered without `_wrap()` — stateless, confirmed in debtors.py docstring
- All `from bot.handlers.*` imports placed inside `_register_*` methods — lazy to avoid circular imports per Phase 9 decisions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. Handler signature verification (message-only vs message+storage) required reading all 7 handler files, but all matched expected patterns.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Router class is complete and importable without errors
- Ready for Phase 10-02: wire Router into bot/main.py via `router.register_all()` and `bot.labeler.load(router.labeler)`
- No blockers

---
*Phase: 10-router*
*Completed: 2026-02-19*

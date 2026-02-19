---
phase: 10-router
plan: 04
subsystem: infra
tags: [vkbottle, router, fsm, auth-guard, fsm-config, access-control]

# Dependency graph
requires:
  - phase: 10-01
    provides: Router class with _wrap() and registration methods
  - phase: 09-fsm-config
    provides: FSM_CONFIG dict with auth_guard per state
  - phase: 10-03
    provides: /exit handler and router _register_commands()
provides:
  - get_user_role() in bot/utils/db.py — role lookup for auth guard
  - _with_auth_guard() in bot/router.py — per-state auth enforcement
  - FSM_CONFIG-driven _register_states() iteration (RTR-01 gap closed)
affects: [11-handler-migration, 12-cancel]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Auth guard wrapper pattern: _with_auth_guard() reads FSM_CONFIG[state].auth_guard and wraps handler accordingly"
    - "auth_guard='any' skips DB query entirely (IDLE, CONTEXT_SWITCH_CONFIRM)"
    - "auth_guard='seller' allows UserRole.SELLER or UserRole.ADMIN"
    - "auth_guard='admin' allows only UserRole.ADMIN"
    - "Auth failure: send denial message + storage.delete() to prevent stuck FSM state"

key-files:
  created: []
  modified: [bot/utils/db.py, bot/router.py]

key-decisions:
  - "get_user_role() returns Optional[UserRole] (not bool) — allows router to distinguish role levels for seller vs admin guards"
  - "Auth guard imports get_user_role lazily inside _with_auth_guard() — consistent with existing pattern for circular import avoidance"
  - "On auth failure: clear FSM state via storage.delete() so user does not get stuck in an unauthorized state"
  - "_register_states() iterates FSM_CONFIG (not handler_map) — FSM_CONFIG is the iteration source, handler_map is the lookup"
  - "IDLE skipped silently (not in handler_map) — IDLE is handled by forwarded-message handler, not a state handler"

patterns-established:
  - "Router is the single point of auth enforcement for all state handlers"
  - "Adding a new BotState to FSM_CONFIG with a handler automatically gets auth guard applied via _with_auth_guard()"

# Metrics
duration: ~2 min
completed: 2026-02-19
---

# Phase 10 Plan 04: FSM_CONFIG-Driven Router with Auth Guards Summary

**Router._register_states() now iterates FSM_CONFIG and enforces auth_guard per state via _with_auth_guard(), with get_user_role() providing role lookup — closing RTR-01 gap from 10-VERIFICATION.md**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-19T19:30:15Z
- **Completed:** 2026-02-19T19:32:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `get_user_role(vk_user_id: int) -> Optional[UserRole]` added to `bot/utils/db.py` after `is_user_admin()`
  - Queries `AppUser.role` for active users (is_active == True)
  - Returns `Optional[UserRole]` — `UserRole` extends `str` so direct comparison with auth_guard literals works without `.value`
- `from bot.fsm.config import FSM_CONFIG` added to `bot/router.py` top-level imports
- `_with_auth_guard(handler_func, state)` method added to Router class:
  - Reads `FSM_CONFIG[state].auth_guard` to determine guard level
  - `"any"`: storage injection only, no DB query — used by IDLE and CONTEXT_SWITCH_CONFIRM
  - `"seller"`: allows `UserRole.SELLER` or `UserRole.ADMIN`; denies with message + state clear
  - `"admin"`: allows only `UserRole.ADMIN`; denies with distinct message + state clear
- `_register_states()` refactored from hardcoded 17-tuple list to FSM_CONFIG iteration:
  - `handler_map` dict maps `BotState` to handler function (lazy imports preserved)
  - FSM_CONFIG is the iteration source; handler_map provides the lookup
  - IDLE silently skipped (not in handler_map)
- Old `_wrap()` method preserved — still used by `_register_commands()` and `_register_forwarded()`

## Task Commits

Each task was committed atomically:

1. **Task 1: Add get_user_role() to bot/utils/db.py** — `58c56c5` (feat)
2. **Task 2: Refactor router to use FSM_CONFIG with auth guard** — `34fbf06` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `bot/utils/db.py` — Added `get_user_role(vk_user_id: int) -> Optional[UserRole]` after `is_user_admin()`. Queries `AppUser.role` for active user. Returns `None` if not found/inactive.
- `bot/router.py` — (1) Added `FSM_CONFIG` import. (2) Added `_with_auth_guard()` method with role-check logic. (3) Replaced hardcoded states tuple list in `_register_states()` with FSM_CONFIG iteration + handler_map lookup.

## Decisions Made

- `get_user_role()` returns `Optional[UserRole]` instead of a simpler bool — enables the router to distinguish between `seller` and `admin` guards without a separate `is_user_admin()` call.
- Auth guard imported lazily inside `_with_auth_guard()` (not at module top) — consistent with existing `_register_*` pattern; avoids circular import risk.
- On auth failure, `storage.delete()` is called before returning — ensures user does not get stuck in a state they cannot access, which would prevent them from doing anything useful.
- `_register_states()` iterates `FSM_CONFIG.items()` (not `handler_map.items()`) — FSM_CONFIG is the canonical source of truth per RTR-01 requirement.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- RTR-01 gap from 10-VERIFICATION.md is fully closed: Router reads FSM_CONFIG, enforces auth guards
- Phase 10 (Router) is now complete — all 4 plans done, both verification gaps closed (10-03: /exit; 10-04: FSM_CONFIG + auth guards)
- Phase 11 (handler migration) can proceed — router is the single auth enforcement point; handlers themselves need no auth logic
- Phase 12 (/cancel back-navigation) can use FSM_CONFIG's `back_state` field; auth guard is already in place at the router level

---
*Phase: 10-router*
*Completed: 2026-02-19*

---
phase: 09-fsm-config-steps
plan: 01
subsystem: fsm
tags: [vkbottle, fsm, dataclass, state-machine, config]

# Dependency graph
requires:
  - phase: 08-foundation
    provides: BotState enum in bot/fsm/states.py
provides:
  - StateConfig dataclass with 6 fields (state, input_type, auth_guard, handler, back_state, forward_states)
  - FSM_CONFIG dict mapping all 18 BotState members to StateConfig entries
  - Single source of truth for FSM navigation and authorization
affects:
  - 09-02 (step functions read FSM_CONFIG for state transitions)
  - 10-router (reads FSM_CONFIG to auto-register vkbottle handlers)
  - 12-cancel-navigation (reads back_state from FSM_CONFIG for /cancel)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Declarative FSM config: all state behavior described in a single dict, not scattered across handlers"
    - "handler=None pattern: config wired in separate phase to avoid circular imports"
    - "Annotated ambiguity: AWAITING_ROW.back_state carries inline comment flagging Phase 12 resolution need"

key-files:
  created:
    - bot/fsm/config.py
  modified: []

key-decisions:
  - "FSM_CONFIG keyed by BotState enum member (not string value) — type-safe dict access"
  - "handler=None in Phase 9 — Phase 10 Router wires real handlers to avoid premature coupling"
  - "No export in bot/fsm/__init__.py — config imported directly to prevent accidental circular imports"
  - "CONTEXT_SWITCH_CONFIRM.back_state=None — no meaningful back state (interrupt flow)"
  - "IDLE.back_state=None — root state has nowhere to go back to"

patterns-established:
  - "StateConfig: declarative per-state metadata used by router and navigation"
  - "forward_states: informational graph edges — not enforced, documents possible transitions"
  - "auth_guard Literal: 'any' | 'seller' | 'admin' — three-tier access without importing UserRole"

# Metrics
duration: 1min
completed: 2026-02-19
---

# Phase 9 Plan 01: FSM Config Summary

**StateConfig dataclass and FSM_CONFIG dict covering all 18 BotState members — declarative single source of truth for FSM behavior used by Phase 10 Router and Phase 12 /cancel navigation**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-19T18:27:11Z
- **Completed:** 2026-02-19T18:28:21Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `bot/fsm/config.py` with `StateConfig` dataclass (6 fields: state, input_type, auth_guard, handler, back_state, forward_states)
- Populated `FSM_CONFIG` dict with all 18 BotState entries, each specifying input_type, auth_guard, back_state, and forward_states
- All handler fields set to None — Phase 10 Router wires actual handlers
- Annotated AWAITING_ROW.back_state ambiguity for Phase 12 resolution

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bot/fsm/config.py with StateConfig and FSM_CONFIG** - `c639115` (feat)

**Plan metadata:** (to be added)

## Files Created/Modified

- `bot/fsm/config.py` — StateConfig dataclass and FSM_CONFIG dict for all 18 BotState members

## Decisions Made

- **FSM_CONFIG keyed by BotState enum:** Type-safe access, prevents typos compared to string keys
- **handler=None in Phase 9:** Avoids premature coupling to handler functions; Phase 10 Router fills these in after all handlers are migrated
- **No bot/fsm/__init__.py export:** Importing config.py directly when needed prevents circular import risk (handlers import from fsm, config could import from handlers in Phase 10)
- **auth_guard uses Literal not UserRole import:** Keeps config.py dependency-free from models layer

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `bot/fsm/config.py` is importable and passes all verification checks
- Phase 9 Plan 02 (step functions) can import `FSM_CONFIG` directly from `bot.fsm.config`
- Phase 10 Router can iterate `FSM_CONFIG.values()` to register vkbottle handlers
- Phase 12 /cancel can read `FSM_CONFIG[current_state].back_state` for navigation
- AWAITING_ROW.back_state ambiguity is documented — Phase 12 must resolve via user context before implementing

---
*Phase: 09-fsm-config-steps*
*Completed: 2026-02-19*

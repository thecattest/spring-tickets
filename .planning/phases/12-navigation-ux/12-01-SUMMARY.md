---
phase: 12-navigation-ux
plan: 01
subsystem: bot
tags: [fsm, navigation, cancel, vkbottle, redis]

# Dependency graph
requires:
  - phase: 09-fsm-config
    provides: FSM_CONFIG with back_state for every BotState
  - phase: 11-handler-migration
    provides: texts.py with all message constants, handlers wired to texts module
provides:
  - Back-step /cancel handler driven by FSM_CONFIG.back_state
  - MSG_CANCEL_ALREADY_IDLE text constant for IDLE no-op
  - ERR_ROW_NO_AVAILABLE_SEATS / ERR_ROW_NO_BOOKED_SEATS / ERR_ROW_NO_RESERVED_SEATS constants (for Plan 12-02)
affects: [12-02-early-row-validation, 12-03-seat-addition-back]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - FSM_CONFIG-driven back navigation via back_state lookup
    - Lazy imports inside cancel_handler for all bot.* dependencies
    - Payload preservation on back-navigation via **state_peer.payload

key-files:
  created: []
  modified:
    - bot/handlers/commands.py
    - bot/texts.py

key-decisions:
  - "cancel_handler uses lazy imports inside function body (FSM_CONFIG, BotState, show_main_menu, db, keyboards) — no circular import risk"
  - "AWAITING_ROW ambiguity resolved via from_main_menu flag in payload — checked BEFORE generic back_state dispatch"
  - "CONTEXT_SWITCH_CONFIRM special case: restores original_state/original_context from payload; falls through to clear-IDLE if original_state missing"
  - "get_empty_keyboard() lazy-imported inside function body, consistent with lazy import pattern"

patterns-established:
  - "back-navigation pattern: read state_peer, extract back_state from FSM_CONFIG, dispatch by back_state value"
  - "MAIN_MENU back navigation calls show_main_menu() directly — handles state set internally"
  - "RESERVE_ACTION back navigation re-queries reserves list (always fresh data)"
  - "Row-entry states (AWAITING_ROW/DELETING_ROW/RESERVE_ADDING_ROW/RESERVE_REMOVING_ROW) share _BACK_PROMPTS lookup dict"

# Metrics
duration: 2min
completed: 2026-02-19
---

# Phase 12 Plan 01: Cancel Back-Navigation Summary

**FSM_CONFIG-driven /cancel back-step navigation: billeters now navigate one step back instead of losing all progress, with AWAITING_ROW from_main_menu ambiguity resolved and CONTEXT_SWITCH_CONFIRM state restoration**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-19T20:48:22Z
- **Completed:** 2026-02-19T20:50:15Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Rewrote cancel_handler to read `FSM_CONFIG[current_state].back_state` and navigate one step back
- IDLE no-op: sends `MSG_CANCEL_ALREADY_IDLE` instead of clearing (already clear)
- AWAITING_ROW ambiguity: checks `from_main_menu` flag — routes to MAIN_MENU (with full menu display) or IDLE
- CONTEXT_SWITCH_CONFIRM: restores `original_state` + `original_context` from payload, sends MSG_CONTINUE_WITH
- MAIN_MENU back_state: calls `show_main_menu()` which handles state transition internally
- RESERVE_ACTION back_state: re-fetches fresh reserves list and displays with `reserve_action_keyboard()`
- Other row-entry back_states: sends appropriate prompt via `_BACK_PROMPTS` dict, updates FSM state
- Added 4 text constants: `MSG_CANCEL_ALREADY_IDLE` (NAV-01) + 3 early row validation messages (NAV-03, for Plan 12-02)
- `exit_handler` unchanged — still hard-resets to IDLE

## Task Commits

Each task was committed atomically:

1. **Task 1: Add text constants for cancel back-navigation** - `ca75954` (feat)
2. **Task 2: Rewrite cancel_handler for FSM_CONFIG back-step navigation** - `a971e98` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `bot/handlers/commands.py` - Rewrote cancel_handler with FSM_CONFIG back-step logic; exit_handler unchanged
- `bot/texts.py` - Added MSG_CANCEL_ALREADY_IDLE and 3 ERR_ROW_NO_* constants

## Decisions Made

- Lazy imports for all bot.* inside cancel_handler body: `BotState`, `FSM_CONFIG`, `show_main_menu`, `db`, `format_reserves_list`, `reserve_action_keyboard`, `get_empty_keyboard` — prevents circular imports consistent with [09-steps] and [10-router] patterns
- AWAITING_ROW check is guarded BEFORE the generic back_state dispatch (step 6 before step 7) — ensures the ambiguity resolution always fires correctly
- CONTEXT_SWITCH_CONFIRM handled as step 4 (before step 5 clear-IDLE) — if original_state is missing, falls through naturally to the clear-IDLE path
- `get_empty_keyboard` is lazy-imported inside function body (not added to module-level imports), consistent with all-lazy-inside-function pattern

## Deviations from Plan

None - plan executed exactly as written. The only additional discovery was that `get_empty_keyboard` was called without being imported at module level (only `commands_keyboard` was imported), which was a [Rule 3 - Blocking] fix: added `from bot.keyboards import get_empty_keyboard` as a lazy import inside the else branch before use.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added lazy import of get_empty_keyboard inside function body**

- **Found during:** Task 2 (Rewrite cancel_handler)
- **Issue:** `get_empty_keyboard()` called in else-branch prompt dispatch but not imported at module level or inside function
- **Fix:** Added `from bot.keyboards import get_empty_keyboard` at start of else-branch (lazy import inside function body)
- **Files modified:** bot/handlers/commands.py
- **Verification:** `python3 -c "from bot.handlers.commands import cancel_handler; print('import ok')"` passes
- **Committed in:** a971e98 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — missing import)
**Impact on plan:** Necessary for execution; consistent with lazy import pattern established in earlier phases.

## Issues Encountered

None — implementation straightforward once all FSM state relationships were confirmed from FSM_CONFIG.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 12-01 cancel back-navigation complete and committed
- `bot/texts.py` already has the 3 `ERR_ROW_NO_*` constants ready for Plan 12-02 (early row validation)
- FSM_CONFIG back_state mappings verified: all 17 states have correct back_state values
- No blockers for Plan 12-02

---
*Phase: 12-navigation-ux*
*Completed: 2026-02-19*

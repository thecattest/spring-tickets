---
phase: 11
plan: 02
subsystem: bot-handlers
tags: [deletion, steps-wiring, texts-wiring, dead-code-removal, handler-migration]

dependency-graph:
  requires:
    - "09-steps: handle_row_input, handle_seat_input, handle_confirmation implemented"
    - "09-foundation: texts.py and constants.py built"
    - "10-router: router owns registration, register_handlers() is dead code"
  provides:
    - "deletion.py migrated — no register_handlers(), uses shared steps and texts"
  affects:
    - "11-03 through 11-08: same migration pattern for remaining handler files"

tech-stack:
  added: []
  patterns:
    - "Lazy imports inside handler bodies (handle_row_input, handle_seat_input, handle_confirmation)"
    - "handle_seat_input(mode='membership') for deletion membership + paid-status validation"
    - "handle_confirmation() returning True/False/None replaces raw string comparisons"
    - "texts.* constants replace all inline message strings"

file-tracking:
  created: []
  modified:
    - bot/handlers/deletion.py

decisions:
  - id: "11-02-lazy-steps"
    summary: "Steps imports kept lazy inside function bodies — consistent with 09-steps decision"
    rationale: "Avoids circular import risk at module level; established pattern"
  - id: "11-02-membership-mode"
    summary: "handle_seat_input(mode='membership') covers both not-in-reservation and paid-seat checks"
    rationale: "Replaces ~35 lines of inline validation; membership mode already handles both error cases"

metrics:
  duration: "~2 min"
  completed: "2026-02-19"
  tasks-completed: 1
  tasks-total: 1
---

# Phase 11 Plan 02: Deletion Handler Migration Summary

**One-liner:** Removed `register_handlers()` and 4 closure wrappers from `deletion.py`; wired `handle_row_input`, `handle_seat_input(mode="membership")`, `handle_confirmation()`, and `texts.*` constants.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove dead code and wire shared infrastructure in deletion.py | 4406441 | bot/handlers/deletion.py |

## What Was Built

`bot/handlers/deletion.py` now:
- Has no `register_handlers(bot)` function — router owns all registration
- Has no inner closure wrappers (`deleting_row_with_storage`, etc.)
- Does not import `Bot` from vkbottle
- Imports `from bot import texts` at module level
- Uses lazy `from bot.steps import handle_row_input` inside `deleting_row_handler`
- Uses lazy `from bot.steps import handle_seat_input` inside `deleting_seats_handler`
- Uses lazy `from bot.steps import handle_confirmation` inside `deletion_confirm_handler` and `cancel_confirm_handler`
- All inline error/prompt/result strings replaced with `texts.*` constants
- All handler signatures unchanged: `(message: Message, storage: RedisStorage)`

Net: 140 lines deleted, 43 insertions (net -97 lines, ~70% reduction in deletion.py)

## Decisions Made

1. **Lazy steps imports inside function bodies** — consistent with 09-steps decision that established this pattern to avoid circular imports. No module-level imports from `bot.steps`.

2. **`handle_seat_input(mode="membership")`** — replaces the entire inline membership/paid-status check block (~35 lines) in `deleting_seats_handler`. The membership mode covers both error cases: seats not in reservation and seats already paid.

3. **`texts.ERR_CONTEXT_LOST` and `texts.ERR_CONTEXT_LOST_FWD`** — used as appropriate for each handler's context-loss message. `deleting_seats_handler` uses `ERR_CONTEXT_LOST_FWD` (points back to forwarded message); `deletion_confirm_handler` and `cancel_confirm_handler` use `ERR_CONTEXT_LOST`.

4. **`texts.MSG_CANCELLED_BRIEF`** — used for the `confirmed is False` branch in both confirmation handlers, replacing the inline `"Отменено."`.

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

- **11-03 (reserve.py):** Ready. Same migration pattern applies. Note that reserve.py has 8 closures (more complex) and a dead `elif text.startswith("/"):` block to remove.
- No blockers introduced.

## Authentication Gates

None.

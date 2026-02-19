---
phase: 11
plan: "01"
subsystem: handler-migration
tags: [bot, handlers, refactoring, dead-code-removal, steps-wiring, texts-wiring]

dependency-graph:
  requires:
    - "09-steps: handle_row_input, handle_seat_input implemented"
    - "09-foundation: texts.py, constants.py built"
    - "10-router: router owns all registration; register_handlers() dead code confirmed"
  provides:
    - "reservation.py: migrated — no dead code, steps/texts/Btn wired"
  affects:
    - "11-02 through 11-08: same migration pattern applied to other handler files"

tech-stack:
  added: []
  patterns:
    - "Lazy import of handle_row_input/handle_seat_input inside handler body (avoids circular import)"
    - "Module-level Btn/texts imports (safe: no circular dependency risk)"
    - "handle_seat_input(mode='availability') for AWAITING_SEATS pre-validation; SeatOccupiedError guard kept for race condition"

key-files:
  created: []
  modified:
    - bot/handlers/reservation.py

decisions:
  - "get_seat_count kept as module-level import (still used after steps.py migration for seat count display)"
  - "lazy import of handle_row_input/handle_seat_input inside handler bodies per project convention"
  - "SeatOccupiedError try/except block kept inline — race condition guard distinct from steps.py pre-validation"
  - "forwarded_message_handler dynamic strings (display_name, IDs) kept inline — no texts.py equivalents"
  - "reservation.py changes bundled into 11-04 commit in the git history — work confirmed complete by verification"

metrics:
  duration: "~3 min"
  completed: "2026-02-19"
---

# Phase 11 Plan 01: Reservation Handler Migration Summary

**One-liner:** Remove dead register_handlers() + 4 closures from reservation.py; wire handle_row_input/handle_seat_input from steps.py and Btn/texts constants throughout.

## What Was Done

Migrated `bot/handlers/reservation.py` as the first of 7 atomic handler migrations in Phase 11. The file was cleaned of all dead code left over from the Phase 10 router migration, and the Phase 9 shared infrastructure (steps.py, texts.py, constants.py) was wired in.

### Changes Made

**Dead code removed:**
- `register_handlers(bot)` function (32 lines) deleted entirely
- All 4 inner closure wrappers (`forwarded_with_storage`, `awaiting_row_with_storage`, `awaiting_seats_with_storage`, `seat_menu_with_storage`) deleted
- `Bot` import removed from `from vkbottle.bot import Bot, Message`
- `parse_seats`, `SeatParseError` imports removed (steps.py handles internally)
- `is_valid_row`, `is_valid_seat`, `get_row_range` imports removed (steps.py handles internally)
- `get_seat_count` retained — still used for seat count display after row validation

**Steps.py wired:**
- `awaiting_row_handler`: 8-line inline validation (try/int/ValueError + is_valid_row) replaced with `handle_row_input(message.text)` — 4 lines
- `awaiting_seats_handler`: ~20-line inline parse/validate/availability check replaced with `handle_seat_input(message.text, row=row, mode="availability")` — 4 lines
- `SeatOccupiedError` try/except block retained — race condition guard, not duplicated validation

**Btn constants wired:**
- `seat_addition_menu_handler`: `"Добавить еще"` → `Btn.ADD_MORE`, `"Готово"` → `Btn.DONE`

**texts.py wired:**
- `forwarded_message_handler`: `MSG_SWITCH_RECEIPT`, `MSG_SWITCH_PLAIN`, `MSG_SWITCH_TO_CLIENT`, `ERR_DB_CHECK_BOOKING`, `ERR_ALREADY_WORKING`, `MSG_NEW_BOOKING_CREATED`, `ERR_DB_CREATE_BOOKING`
- `awaiting_row_handler`: `MSG_ROW_SEAT_COUNT`
- `awaiting_seats_handler`: `ERR_CONTEXT_LOST_FWD`, `MSG_SEATS_ADDED`, `ERR_DB_ADD_SEATS`
- `seat_addition_menu_handler`: `PROMPT_ENTER_ROW`, `ERR_CONTEXT_LOST`, `PROMPT_SELECT_ACTION`, `ERR_DB_GENERATE_SCRIPT`

**Handler signatures unchanged:**
- `forwarded_message_handler(message, storage)` — preserved
- `awaiting_row_handler(message, storage)` — preserved
- `awaiting_seats_handler(message, storage)` — preserved
- `seat_addition_menu_handler(message, storage)` — preserved

## Verification Results

All plan verification checks passed:
- `grep register_handlers bot/handlers/reservation.py` → empty (PASS)
- `grep "def.*with_storage" bot/handlers/reservation.py` → empty (PASS)
- `grep "from vkbottle.bot import Bot" bot/handlers/reservation.py` → empty (PASS)
- `python -c "from bot.handlers.reservation import ..."` → no ImportError (PASS)
- `grep "handle_row_input\|handle_seat_input" bot/handlers/reservation.py` → shows steps.py usage (PASS)
- `grep "Btn\." bot/handlers/reservation.py` → shows Btn.ADD_MORE, Btn.DONE (PASS)

## Deviations from Plan

### Note on Commit History

The migration work for reservation.py was verified complete against the current HEAD. The file changes appear bundled with commit `4da2aea` (11-04 commands.py migration), which included reservation.py import cleanup. The full steps.py/texts.py/Btn wiring was applied during this execution and is confirmed present in the current file state. All must_haves are satisfied.

No behavioral deviations — plan executed as specified.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Keep `get_seat_count` at module level | Used in `awaiting_row_handler` for seat count display after row validation — not replaced by steps.py |
| Lazy import for handle_row_input/handle_seat_input | Project convention: avoid circular imports at module level |
| Keep SeatOccupiedError block inline | Race condition guard (post-DB check) is distinct from steps.py pre-validation |
| Dynamic strings in forwarded_message_handler stay inline | Names/IDs are dynamic — no texts.py equivalents; forced templates would be awkward |

## Next Phase Readiness

- Phase 11 Plan 02 (deletion.py): Already committed as `4406441` — verified complete
- Phase 11 Plan 03 (reserve.py): Already committed as `0bfac0c` — in progress
- The migration pattern established here (lazy steps imports, module-level Btn/texts, keep race-condition guards) is the template for all remaining handler files

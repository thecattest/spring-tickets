---
phase: 04-admin-reserve-management
plan: 01
subsystem: database
tags: [vkbottle, sqlalchemy, fsm, seat-assignment, reserve, audit-log]

# Dependency graph
requires:
  - phase: 03-payment-recording
    provides: "Established pattern: FSM states, keyboard generators, DB functions with audit logging"
  - phase: 01-core-reservation
    provides: "SeatAssignment model, SeatStatus.RESERVED, SeatOccupiedError, SessionLocal pattern"
provides:
  - 7 new BotState values for reserve flow (RESERVE_ACTION through RESERVE_REMOVE_CONFIRM)
  - reserve_action_keyboard() with Добавить резерв / Удалить резерв buttons
  - get_app_user_by_vk_id() — resolve AppUser.id from VK user ID
  - add_reserve() — atomic RESERVED seat creation with note, audit log
  - release_reserve() — release RESERVED seats, return previous notes, audit log
affects:
  - 04-02 (reserve handler uses all three DB functions and both states/keyboard)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reserve seats: SeatAssignment with status=RESERVED, reservation_id=None (not tied to reservation)"
    - "Admin identity: resolve AppUser.id via get_app_user_by_vk_id before DB writes (never store VK user ID as creator)"
    - "Atomic availability check: loop seats before any insert, raise SeatOccupiedError on first conflict"
    - "Audit log for reserve: action_type=reserve_added / reserve_removed with row, seats, comment/previous_notes"

key-files:
  created: []
  modified:
    - "bot/fsm/states.py"
    - "bot/keyboards.py"
    - "bot/utils/db.py"

key-decisions:
  - "Reserve seats have reservation_id=None — reserves are NOT tied to any reservation"
  - "Admin's AppUser.id (not VK user ID) stored as created_by_user_id — get_app_user_by_vk_id resolves this"
  - "release_reserve returns previous notes list for audit display in handler"
  - "release_reserve raises DatabaseError (not SeatOccupiedError) when seats not found as RESERVED"

patterns-established:
  - "Pattern: DB function receives user_id=AppUser.id, not VK user ID (caller resolves via get_app_user_by_vk_id)"
  - "Pattern: release_reserve collects notes before modifying rows (consistent snapshot)"

# Metrics
duration: 6min
completed: 2026-02-18
---

# Phase 4 Plan 01: Admin Reserve Management Foundation Summary

**FSM states, reserve_action_keyboard, and three atomic DB functions (add_reserve, release_reserve, get_app_user_by_vk_id) for admin reserve management using SeatStatus.RESERVED with reservation_id=None**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-17T23:30:23Z
- **Completed:** 2026-02-17T23:37:15Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- 7 new BotState values for the complete reserve flow (add path and remove path)
- reserve_action_keyboard with primary/negative button pair for admin action selection
- get_app_user_by_vk_id resolves VK user ID to AppUser.id (required so created_by_user_id is correct internal ID)
- add_reserve creates RESERVED SeatAssignment rows atomically with note=comment and reservation_id=None
- release_reserve releases active RESERVED seats, collects previous notes for audit display, commits audit log

## Task Commits

Each task was committed atomically:

1. **Task 1: Add FSM states and reserve action keyboard** - `671dac1` (feat)
2. **Task 2: Add reserve database functions** - `ca3d4e7` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified
- `bot/fsm/states.py` - 7 new BotState values + reserve flow diagrams in docstring
- `bot/keyboards.py` - reserve_action_keyboard() function
- `bot/utils/db.py` - get_app_user_by_vk_id, add_reserve, release_reserve functions

## Decisions Made
- Reserve seats use reservation_id=None: reserves are admin-only hold seats not tied to any customer reservation
- Admin identity stored as AppUser.id (internal), not VK user ID: get_app_user_by_vk_id provides the bridge at the handler level
- release_reserve returns List[dict] with previous notes so the handler can show what was in the note field before clearing (useful for audit display in the bot message)
- release_reserve raises DatabaseError (not SeatOccupiedError) when seats not found as active RESERVED — different semantic (not "seat taken" but "seat not in expected state")

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- vkbottle and redis packages not installed for python3.14 — installed via pip during verification. Pre-existing environment setup gap, not caused by code changes.
- Pre-existing test failures in test_seat_parser.py (error message mismatch) and test_db_integration.py (Redis/DB environment) — confirmed pre-existing, not introduced by this plan.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All foundation components ready for Plan 02 (reserve handler)
- Handler needs: RESERVE_ACTION, RESERVE_ADDING_ROW/SEATS, RESERVE_COMMENT, RESERVE_REMOVING_ROW/SEATS, RESERVE_REMOVE_CONFIRM states
- Handler needs: reserve_action_keyboard(), add_reserve(), release_reserve(), get_app_user_by_vk_id()
- Admin check: is_user_admin() already exists in db.py from Phase 2 Plan 03

---
*Phase: 04-admin-reserve-management*
*Completed: 2026-02-18*

---
phase: 11-handler-migration
plan: 06
subsystem: bot
tags: [vkbottle, fsm, constants, texts, payment]

# Dependency graph
requires:
  - phase: 08-foundation
    provides: Btn constants (Btn.CANCEL, Btn.PAY_ALL_PREFIX) and texts.py message constants
  - phase: 10-router
    provides: Router registers payment_quantity_handler directly — register_handlers() now dead code
provides:
  - Migrated bot/handlers/payment.py: register_handlers removed, Btn and texts wired
affects:
  - 11-07-handler-migration (next handler file migrations)
  - 11-08-handler-migration (main.py cleanup)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Handler files import Btn from bot.constants and texts from bot for all constants"
    - "register_handlers() + closure pattern fully removed from payment.py"

key-files:
  created: []
  modified:
    - bot/handlers/payment.py

key-decisions:
  - "text[len(Btn.PAY_ALL_PREFIX):] used instead of text[4:] — self-documents the prefix, avoids magic number"
  - "start_payment_flow inline prompt string kept as-is — not in texts.py, too dynamic/contextual"

patterns-established:
  - "Migration pattern: remove Bot import + closure + register_handlers, add Btn + texts imports"

# Metrics
duration: 1min
completed: 2026-02-19
---

# Phase 11 Plan 06: Payment Handler Migration Summary

**payment.py dead code removed and wired to Btn.CANCEL, Btn.PAY_ALL_PREFIX, and 9 texts.* constants**

## Performance

- **Duration:** 1 min
- **Started:** 2026-02-19T20:10:33Z
- **Completed:** 2026-02-19T20:11:47Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Deleted `register_handlers()` function and `payment_quantity_with_storage` closure (14 lines removed)
- Replaced `Bot` import with `from bot.constants import Btn` and `from bot import texts`
- Wired `Btn.CANCEL` for the cancel button comparison and `Btn.PAY_ALL_PREFIX` for the pay-all startswith check
- Replaced 9 inline string literals with `texts.*` constants: `ERR_CONTEXT_LOST`, `ERR_DB_LOAD_BOOKING`, `ERR_DB_CHECK_SEATS`, `ERR_DB_RECORD_PAYMENT`, `ERR_QTY_EXCEEDS`, `ERR_INSUFFICIENT_SEATS`, `PROMPT_SELECT_QUANTITY`, `PROMPT_MIN_QUANTITY`, `MSG_NO_SEATS_FOR_PAYMENT`

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove dead code and wire constants in payment.py** - `0b3dc21` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `bot/handlers/payment.py` - Migrated: register_handlers removed, Btn + texts wired, 18 insertions / 34 deletions net -16 lines

## Decisions Made

- Used `text[len(Btn.PAY_ALL_PREFIX):]` instead of `text[4:]` — self-documents the prefix boundary, avoids a magic number that would silently break if the prefix ever changed
- The inline `start_payment_flow` prompt (`"Бронь — {buyer_display_name}\n\n..."`) was not in texts.py and is highly contextual; left as inline per plan instruction to only replace *matching* texts.* constants

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- payment.py is fully migrated; router already calls `payment_quantity_handler` directly
- Remaining handler files (debtors.py, forwarded.py, etc.) can proceed with identical migration pattern
- No blockers

---
*Phase: 11-handler-migration*
*Completed: 2026-02-19*

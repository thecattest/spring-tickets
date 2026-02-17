---
phase: 03-payment-recording
plan: 02
subsystem: payments
tags: [vkbottle, fsm, payment-flow, receipt-forwarding, circular-imports]

# Dependency graph
requires:
  - phase: 03-01
    provides: payment_quantity_keyboard, record_payment, InsufficientSeatsError, format_payment_confirmation, PAYMENT_QUANTITY state
  - phase: 02-02
    provides: show_main_menu, main_menu_keyboard, main_menu_handler, FSM context structure
  - phase: 02-04
    provides: buyer_vk_api_id in FSM context for same-client detection
provides:
  - bot/handlers/payment.py with start_payment_flow (shared entry point) and payment_quantity_handler
  - MAIN_MENU + same-client receipt forwarding triggers payment flow
  - MAIN_MENU + different-client receipt forwarding shows error (no context switch)
  - "Оплата" button routes to payment flow via local import
  - Payment handlers registered in bot startup
affects: [phase 4 (debt reminders), any future phase touching payment or receipt flows]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Local import inside function to break circular dependency (payment.py imports menu.py locally, menu.py imports payment.py locally)
    - datetime.isoformat() for serializing timestamps to FSM context (Redis stores strings)
    - Shared entry point pattern: start_payment_flow serves both receipt-forward and button flows

key-files:
  created:
    - bot/handlers/payment.py
  modified:
    - bot/handlers/reservation.py
    - bot/handlers/menu.py
    - bot/main.py

key-decisions:
  - "Use local import inside payment_quantity_handler and menu.py Oplata block to avoid circular dependency between payment.py and menu.py"
  - "Serialize vk_message_ts as ISO string in FSM context (datetime objects not JSON-serializable); deserialize with datetime.fromisoformat() on retrieval"
  - "MAIN_MENU + different-client receipt forwarding shows error with main_menu_keyboard (no context switch prompt) - user must use button flow for current client"

patterns-established:
  - "Circular import avoidance: use local imports inside functions for mutual dependencies (menu.py <-> payment.py)"
  - "Timestamp serialization: convert datetime to isoformat string for FSM storage, parse back on retrieval"
  - "Shared entry point: start_payment_flow handles both receipt-forward and button payment flows with uniform state transition"

# Metrics
duration: 3min
completed: 2026-02-18
---

# Phase 3 Plan 02: Payment Handlers Summary

**Payment flow fully wired: receipt forwarding and button both trigger quantity selection keyboard, record_payment called on confirmation, confirmation message with remaining seats shown**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-17T21:24:34Z
- **Completed:** 2026-02-17T21:28:07Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Created bot/handlers/payment.py with complete payment flow: start_payment_flow entry point, payment_quantity_handler for PAYMENT_QUANTITY state
- Wired receipt forwarding: MAIN_MENU + same client forward now triggers payment flow; different client forward shows error with main_menu_keyboard (stays in MAIN_MENU, no context switch)
- Replaced "Оплата" placeholder in menu.py with real start_payment_flow call using local import to avoid circular dependency
- Registered payment handlers in bot startup (bot/main.py)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create payment handler + wire receipt forwarding** - `f56ddc8` (feat)
2. **Task 2: Wire menu button + register handlers** - `2ccda4d` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified
- `bot/handlers/payment.py` - Payment flow handlers: start_payment_flow, payment_quantity_handler, register_handlers
- `bot/handlers/reservation.py` - Added MAIN_MENU receipt forwarding branches (same-client = payment, different-client = error); imported main_menu_keyboard
- `bot/handlers/menu.py` - Replaced "Оплата" placeholder with start_payment_flow local import call
- `bot/main.py` - Added payment module import and payment.register_handlers(bot) registration

## Decisions Made
- **Local import pattern for circular dependency:** payment.py needs show_main_menu from menu.py; menu.py needs start_payment_flow from payment.py. Solution: both use local imports inside their respective functions (inside payment_quantity_handler and inside the `elif text == "Оплата"` block). This is a clean, established Python pattern.
- **Serialize vk_message_ts as ISO string in FSM context:** datetime objects aren't JSON-serializable; FSM context (Redis) stores strings. Solution: `vk_message_ts.isoformat()` on store, `datetime.fromisoformat()` on retrieve.
- **Different-client MAIN_MENU receipt: no context switch:** When seller is in MAIN_MENU with client A and forwards a receipt from client B, show a clear error message (not a context switch prompt) and stay in MAIN_MENU. The "Оплата" button is the correct flow for client A.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- vkbottle not installed in system Python 3.14; needed to use project's `.venv/bin/python` for import verification. This is expected (virtual environment usage).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Full payment recording flow operational: both receipt-forward and button flows functional
- Phase 3 complete (both plans 01 and 02 done)
- Phase 4 (debt reminders) can now rely on payment status in database (BOOKED vs PAID seat counts)
- No blockers

---
*Phase: 03-payment-recording*
*Completed: 2026-02-18*

---
phase: "03"
plan: "03"
name: "Gap Closure: Receipt Forwarding Bugs"
subsystem: "payment-flow"
tags: ["vkbottle", "fsm", "receipt-forwarding", "context-switch", "bug-fix", "payment"]

dependency-graph:
  requires:
    - "03-02: Payment handlers (start_payment_flow, payment_quantity_handler)"
    - "02-04: Same-client detection via buyer_vk_api_id"
  provides:
    - "Correct receipt vs plain-text forwarding detection"
    - "Working MAIN_MENU receipt routing (state comparison fix)"
    - "Context switch with pending_is_receipt for receipt-triggered switches"
    - "IDLE + receipt + existing reservation -> direct payment flow"
  affects:
    - "Phase 4: Any future forwarded message handling builds on fixed routing"

tech-stack:
  added: []
  patterns:
    - "str(BotState.X) for vkbottle FSM state comparison (not .value)"
    - "forwarded_has_receipt_attachment helper for attachment-based receipt detection"
    - "pending_is_receipt flag in CONTEXT_SWITCH_CONFIRM state for deferred payment routing"
    - "ISO string serialization of datetime in FSM context (established in 03-02, extended here)"

file-tracking:
  created: []
  modified:
    - "bot/handlers/reservation.py"
    - "bot/handlers/menu.py"

decisions:
  - id: "D1"
    choice: "str(BotState.X) for FSM state comparison throughout codebase"
    rationale: "vkbottle stores state as 'BotState:main_menu' not 'main_menu'; .value returns only the raw value which never matches"
    impact: "All MAIN_MENU branches were dead code; fix makes them live"
  - id: "D2"
    choice: "Attachment-based receipt detection (photo or doc) via forwarded_has_receipt_attachment helper"
    rationale: "Receipts are always images or documents; plain text forwards should not trigger payment"
    impact: "Plain text forwards now re-show menu or offer context switch instead of entering payment flow"
  - id: "D3"
    choice: "pending_is_receipt flag stored in CONTEXT_SWITCH_CONFIRM state"
    rationale: "Context switch confirmation happens in a separate state; need to carry receipt intent across state boundary"
    impact: "After confirming switch, payment flow is entered immediately without requiring another forward"
  - id: "D4"
    choice: "IDLE + receipt + existing reservation enters payment flow without re-showing main menu first"
    rationale: "Forwarding a receipt from IDLE with existing reservation implies intent to record payment; skipping menu step reduces friction"
    impact: "Direct path from receipt forward to payment quantity keyboard for IDLE sellers"
  - id: "D5"
    choice: "MAIN_MENU + different client + plain text -> context switch offer (not error)"
    rationale: "UAT test 7 required context switch for different-client forwards; error was wrong-client receipts only"
    impact: "Plain text forwards from different clients now correctly offer context switch"

metrics:
  duration: "3 minutes (171 seconds)"
  completed: "2026-02-18"
  tasks-completed: 2
  tasks-total: 2
  commits: 2
---

# Phase 03 Plan 03: Gap Closure — Receipt Forwarding Bugs Summary

**One-liner:** Fixed MAIN_MENU dead-code bug (BotState.value vs str()), added attachment-based receipt detection, and wired context switch to payment flow via pending_is_receipt flag.

## What Was Built

Two targeted fixes to `bot/handlers/reservation.py` and `bot/handlers/menu.py` correcting four bugs found during UAT that prevented receipt forwarding from working correctly.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix forwarded_message_handler — state comparison, attachment detection, receipt routing | f63ad4f | bot/handlers/reservation.py |
| 2 | Update context_switch_handler to support pending_is_receipt payment flow | 431b1a1 | bot/handlers/menu.py |

## Root Cause Analysis

**Bug 1 (Critical): Dead MAIN_MENU branches**
- vkbottle stores FSM state as `str(BotState.MAIN_MENU)` = `"BotState:main_menu"`
- Code compared `current_state == BotState.MAIN_MENU.value` = `"main_menu"`
- These NEVER match — all MAIN_MENU-specific branches were unreachable dead code
- Fix: replace all `.value` comparisons with `str(BotState.MAIN_MENU)`

**Bug 2: Any forward triggered payment**
- No attachment check — any forwarded message in MAIN_MENU triggered payment flow
- Fix: `forwarded_has_receipt_attachment()` helper checks `.photo` or `.doc` on attachments
- Plain text forwards now route to menu re-show (same client) or context switch offer (different client)

**Bug 3: Different client in MAIN_MENU gave error instead of context switch**
- UAT Test 7 failed: different-client receipt forward showed "use Оплата button" error
- Fix: different-client receipt in MAIN_MENU now offers context switch with `pending_is_receipt=True`
- Different-client plain text in MAIN_MENU now offers context switch with `pending_is_receipt=False`

**Bug 4: IDLE + receipt + existing reservation skipped payment**
- Receipt forward from IDLE with existing reservation showed main menu instead of entering payment
- Fix: IDLE + receipt + existing reservation now enters payment flow directly

## Routing Matrix (After Fix)

| State | Client | Forward type | Action |
|-------|--------|-------------|--------|
| MAIN_MENU | Same | Photo/doc (receipt) | `start_payment_flow` |
| MAIN_MENU | Same | Plain text | Re-show main menu |
| MAIN_MENU | Different | Photo/doc (receipt) | Context switch offer (`pending_is_receipt=True`) |
| MAIN_MENU | Different | Plain text | Context switch offer (`pending_is_receipt=False`) |
| Non-MAIN_MENU | Same | Any | "Already working with this client" |
| Non-MAIN_MENU | Different | Any | Context switch offer (with `pending_is_receipt` flag) |
| IDLE | Any | Photo/doc + existing reservation | `start_payment_flow` directly |
| IDLE | Any | Plain text + existing reservation | Show main menu |
| IDLE | Any | Any + no reservation | Create new reservation |

## Context Switch + Receipt Flow (menu.py)

After user confirms context switch ("Да"):
- `pending_is_receipt=True` + existing reservation → set MAIN_MENU state → `start_payment_flow`
- `pending_is_receipt=True` + no reservation → create reservation (can't pay without booking)
- `pending_is_receipt=False` + existing reservation → `show_main_menu` (original behavior)
- `pending_is_receipt=False` + no reservation → create reservation (original behavior)

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| State comparison format | `str(BotState.X)` not `.value` | vkbottle stores full "BotState:x" format |
| Receipt detection | Attachment check (.photo/.doc) | Receipts are always images/docs, not text |
| Cross-state receipt intent | `pending_is_receipt` flag in CONTEXT_SWITCH_CONFIRM | Carry receipt intent across state boundary |
| IDLE receipt shortcut | Skip main menu, go directly to payment | Reduces friction for common receipt-forward flow |
| Different-client MAIN_MENU | Context switch offer (not error) | Error was wrong per UAT test 7 requirements |

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

Phase 4 (Debt Reminders) can begin. Receipt forwarding is now fully functional with correct routing for all client/state/attachment combinations. No blocking issues remain from Phase 3.

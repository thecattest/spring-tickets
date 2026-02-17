---
status: complete
phase: 02-main-menu-seat-management
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md
started: 2026-02-17T12:00:00Z
updated: 2026-02-17T12:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Main menu displays for existing reservation
expected: Forward a message from a client with an active reservation. Bot shows: real VK name, seats grouped by rows with ranges (e.g. "Ряд 5: 1-3, 7"), status emoji (📌 Бронь / ✅ Оплачено / 🔒 Резерв), 4 buttons: [Добавить] [Удалить] / [Удалить все] [Оплата].
result: pass

### 2. Same-client forward handled gracefully
expected: While working with Client A (FSM not IDLE), forward another message from Client A. Bot does NOT show context switch prompt — recognizes same client and continues without interruption.
result: pass

### 3. Context switch prompt for different client
expected: While working with Client A (FSM not IDLE), forward a message from Client B. Bot shows "Сейчас вы работаете с [Name A]. Переключиться на [Name B]?" with [Да] [Нет].
result: pass

### 4. Context switch "Да" switches to new client
expected: Click "Да" on context switch. Bot clears previous context, shows main menu for Client B (if has reservation) or starts new reservation (if no reservation).
result: pass

### 5. Context switch "Нет" restores original
expected: Click "Нет" on context switch. Bot restores original Client A state and continues previous workflow.
result: pass

### 6. Add seats from main menu returns to menu
expected: From main menu click [Добавить], enter row, enter seats, click [Готово]. Bot shows updated main menu with new seats. Does NOT generate script.
result: pass

### 7. Add more seats preserves menu context
expected: When adding seats from menu, click [Добавить еще]. Bot returns to row input. After adding seats and [Готово], returns to main menu (not script).
result: pass

### 8. Delete seats - full flow
expected: From main menu click [Удалить]. Bot prompts for row. Enter valid row. Bot prompts for seats. Enter BOOKED seats. Bot shows confirmation with [Подтвердить] [Отмена].
result: pass

### 9. Delete seats - invalid row rejected
expected: During deletion, enter invalid row (0 or 25+). Bot shows error about valid range (1-24) and re-prompts.
result: pass

### 10. Delete seats - confirm deletes and returns to menu
expected: Click [Подтвердить] on deletion. Seats deleted, success message shown, main menu displayed with updated seat list.
result: pass

### 11. Delete seats - cancel returns to menu
expected: Click [Отмена] on deletion. No seats deleted, main menu shown unchanged.
result: pass

### 12. Delete PAID seats blocked
expected: Try to delete PAID seats. Bot shows "Места уже оплачены, удалить нельзя" and stays in seat input.
result: skipped
reason: "Payment not implemented yet (Phase 3). Will verify in payment phase."

### 13. Cancel reservation - BOOKED only
expected: Click [Удалить все] on reservation with only BOOKED seats. Confirm. Bot cancels reservation, shows "Бронь отменена", returns to IDLE.
result: pass

### 14. Cancel reservation - PAID seats non-admin blocked
expected: Non-admin tries to cancel reservation with PAID seats. Bot shows "В брони есть оплаченные места. Отмена доступна только админам." Returns to menu.
result: skipped
reason: "Payment not implemented yet (Phase 3). Will verify in payment phase."

### 15. Cancel reservation - PAID seats admin allowed
expected: Admin cancels reservation with PAID seats. Bot cancels successfully, shows "Бронь отменена", returns to IDLE.
result: skipped
reason: "Payment not implemented yet (Phase 3). Will verify in payment phase."

## Summary

total: 15
passed: 12
issues: 0
pending: 0
skipped: 3

## Gaps

[none yet]

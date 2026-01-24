---
status: diagnosed
phase: 02-main-menu-seat-management
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md
started: 2026-01-24T04:21:10Z
updated: 2026-01-24T04:43:45Z
---

## Current Test

[testing complete]

## Tests

### 1. Main menu displays for existing reservation
expected: When seller forwards a message from a client who already has an active reservation (with at least one booked seat), bot responds with client display name (real VK first_name + last_name, not "VK User 12345"), all seats grouped by rows (e.g., "Ряд 5: 1-3, 7"), seats grouped by status with emoji indicators (📌 Бронь, ✅ Оплачено, 🔒 Резерв), and four action buttons in 2 rows: [Добавить] [Удалить] on row 1, [Удалить все] [Оплата] on row 2
result: pass

### 2. Context switch confirmation when switching clients
expected: When seller is working with Client A (FSM state is not IDLE) and forwards a message from Client B (different VK user), bot shows warning message "Сейчас вы работаете с [Name A]. Переключиться на [Name B]?" with confirmation keyboard [Да] [Нет]
result: pass

### 3. Context switch "Да" - switches to new client
expected: When seller clicks "Да" on context switch confirmation, bot clears current context and either shows main menu (if Client B has existing reservation) or starts new reservation flow (if Client B has no reservation)
result: pass

### 4. Context switch "Нет" - restores original context
expected: When seller clicks "Нет" on context switch confirmation, bot restores original FSM state and context for Client A and shows appropriate message continuing previous workflow
result: pass

### 5. Same client forward is ignored
expected: When seller is already working with Client A and forwards another message from Client A, bot ignores it (no duplicate work, no confusing messages)
result: issue
reported: "переспрашивает переключиться ли на клиента А, операция с клиентом А будет прервана. и показывает клавиатуру с да / нет"
severity: major

### 6. Add seats from main menu returns to menu
expected: When seller clicks [Добавить] from main menu, enters row and seats, then clicks [Готово], bot shows updated main menu with new seats added (does NOT generate script like Phase 1 flow)
result: pass

### 7. Add seats "Добавить еще" preserves menu context
expected: When adding seats from main menu and clicking [Добавить еще], bot returns to AWAITING_ROW and preserves menu context so final [Готово] returns to menu (not script)
result: pass

### 8. Delete seats - row validation
expected: When seller clicks [Удалить] from main menu, bot prompts "Введите номер ряда:". Entering invalid row (0 or 25+) shows Russian error "Неверный ряд. Допустимые значения: 1-24. Введите ряд:"
result: pass

### 9. Delete seats - seat selection for BOOKED seats
expected: When seller enters valid row number during deletion flow, bot asks "Введите номера мест для удаления:". Entering valid BOOKED seats (e.g., "1-3, 5") shows confirmation message with seat list and [Подтвердить] [Отмена] buttons
result: pass

### 10. Delete seats - PAID seat protection
expected: When seller tries to delete seats that include PAID seats (status=PAID), bot shows error "Места уже оплачены, удалить нельзя" and stays in DELETING_SEATS state asking for different seats
result: skipped
reason: "Оплата еще не реализована (Phase 3). Нужно будет проверить в фазе оплаты"

### 11. Delete seats - confirmation and execution
expected: When seller clicks [Подтвердить] on deletion confirmation, bot deletes the selected BOOKED seats, shows success message with count (e.g., "Удалено мест: 3"), and returns to main menu with updated seat list
result: pass

### 12. Delete seats - cancellation
expected: When seller clicks [Отмена] on deletion confirmation, bot returns to main menu without deleting any seats
result: pass

### 13. Cancel reservation - no PAID seats
expected: When seller clicks [Удалить все] from main menu on a reservation with only BOOKED seats (no PAID), bot shows confirmation and clicking [Подтвердить] cancels entire reservation, shows "Бронь отменена", and clears FSM state (returns to IDLE)
result: pass

### 14. Cancel reservation - PAID seats without admin
expected: When non-admin seller tries to cancel reservation with PAID seats (clicks [Удалить все] → [Подтвердить]), bot shows error "В брони есть оплаченные места. Отмена доступна только админам." and returns to main menu without cancelling
result: skipped
reason: "Оплата еще не реализована (Phase 3). Нужно будет проверить в фазе оплаты"

### 15. Cancel reservation - PAID seats with admin
expected: When admin seller cancels reservation with PAID seats (clicks [Удалить все] → [Подтвердить]), bot successfully cancels reservation including PAID seats, shows "Бронь отменена", and returns to IDLE
result: skipped
reason: "Оплата еще не реализована (Phase 3). Нужно будет проверить в фазе оплаты"

### 16. Seat range formatting works correctly
expected: When viewing reservation seats in main menu, consecutive seats are formatted as ranges (e.g., seats [1,2,3,5,7,8,9] display as "1-3, 5, 7-9")
result: pass

## Summary

total: 16
passed: 12
issues: 1
pending: 0
skipped: 3

## Gaps

- truth: "When seller is already working with Client A and forwards another message from Client A, bot ignores it (no duplicate work, no confusing messages)"
  status: failed
  reason: "User reported: переспрашивает переключиться ли на клиента А, операция с клиентом А будет прервана. и показывает клавиатуру с да / нет"
  severity: major
  test: 5
  root_cause: "ID type mismatch in same-client detection logic (reservation.py:71) - compares VK API user ID (buyer_vk_id from forwarded.from_id) against database primary key (current_buyer_vk_id from context) which will never match even for same client"
  artifacts:
    - path: "bot/handlers/reservation.py"
      issue: "Line 69: Retrieves wrong ID type from context (database primary key instead of VK API ID)"
    - path: "bot/handlers/reservation.py"
      issue: "Line 71: Compares VK API ID to database primary key"
    - path: "bot/handlers/reservation.py"
      issue: "Line 147: Stores database ID in context (needs VK API ID added)"
    - path: "bot/handlers/menu.py"
      issue: "Line 58: Also stores database ID (needs VK API ID added)"
  missing:
    - "Add buyer_vk_api_id field to context (do NOT rename buyer_vk_user_id - used by deletion.py and menu.py for database lookups)"
    - "Update same-client comparison to use buyer_vk_api_id"
  debug_session: ".planning/debug/same-client-forward-ignored.md"

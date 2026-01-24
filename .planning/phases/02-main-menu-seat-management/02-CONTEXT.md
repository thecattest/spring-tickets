# Phase 2: Главное меню и удаление мест - Context

**Gathered:** 2026-01-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Menu-driven interface for managing existing reservations. When a seller forwards a message from a client who already has an active reservation, they can view all seats, add more seats, delete seats, or cancel the entire reservation. Does not include payment functionality (Phase 3).

</domain>

<decisions>
## Implementation Decisions

### Menu presentation and navigation
- When seller forwards message from client with existing reservation → show full seat list immediately
- Display all seats grouped by row with status indicators
- Action buttons below seat list: [Добавить] [Удалить] [Удалить все] [Оплата]
- After adding or deleting seats → automatically return to main menu with updated seat list (no [Готово] button needed)
- Navigation stays in reservation context until seller explicitly exits

### Seat grouping and status display
- Group by row, show status for each group of seats within the row
- Format: "Ряд X: [seats] [status]"
- Status indicators using emoji:
  - 📌Бронь (BOOKED seats)
  - ✅Оплачено (PAID seats)
  - 🔒Резерв (RESERVED seats)
- Show summary counts at top: "Всего мест: X | Бронь: Y | Оплачено: Z"
- Consecutive seats displayed as ranges: "5-9" instead of "5, 6, 7, 8, 9"

### Deletion workflow and validation
- Deletion flow: click [Удалить] → ask for row number → ask for seat numbers
- Seat selection uses same parser as adding seats (spaces/commas/ranges)
- **Validation rules:**
  - If any selected seat is already PAID → block entire deletion with error: "Место X уже оплачено, удалить нельзя"
  - All selected seats must belong to current reservation and be BOOKED status
- Require confirmation before deletion: show selected seats + [Подтвердить] [Отмена] buttons
- [Удалить все] (cancel reservation) rules:
  - If reservation has any PAID seats AND user is NOT admin → block with error: "В брони есть оплаченные места. Отмена доступна только админам"
  - If user is admin OR no PAID seats → allow cancellation after confirmation

### Context conflict handling
- When seller forwards Client B message while working with Client A (FSM not IDLE):
  - Show prompt: "Переключиться на [Client B]? Текущая операция будет отменена" + [Да] [Нет]
  - If [Да] → cancel Client A operation (reset to IDLE), switch to Client B
  - If [Нет] → stay with Client A, ignore Client B forward
- No explicit command to switch clients — only via forwarding messages
- /cancel command behavior:
  - If in middle of operation (adding/deleting seats) → exit operation, return to client's main menu
  - If already at main menu → clear FSM to IDLE, exit all context

### Claude's Discretion
- Exact formatting of seat ranges (e.g., whether to use hyphen or em-dash)
- Confirmation message wording
- Error message details beyond core requirements
- Button layout and spacing

</decisions>

<specifics>
## Specific Ideas

- Keep the interface simple and fast — sellers work quickly, minimal friction
- Use emoji to make status immediately recognizable at a glance
- Atomic operations: if deletion fails validation, block everything (don't partial-delete)
- Context switching is intentional — require confirmation to prevent accidental data loss

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-main-menu-seat-management*
*Context gathered: 2026-01-24*

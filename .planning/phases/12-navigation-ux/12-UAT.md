---
status: complete
phase: 12-navigation-ux
source: [12-01-SUMMARY.md, 12-02-SUMMARY.md]
started: 2026-02-20T10:00:00Z
updated: 2026-02-20T10:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. /cancel in IDLE state
expected: Send /Отмена with no active operation. Bot replies "Вы уже в начальном состоянии." — no state change, no error.
result: pass

### 2. /cancel while entering seat numbers
expected: Start a booking (forward a client message, enter a valid row). While on "enter seat numbers" step, send /Отмена. Bot returns to "enter row number" step (prompts for row again) — does NOT clear to IDLE.
result: pass

### 3. /cancel while entering row (from main menu)
expected: From the main menu, choose "Добавить" (add seats). While on "enter row number" step, send /Отмена. Bot returns to the main menu for that client — does NOT clear to IDLE.
result: pass

### 4. /cancel while entering row (from forwarded message)
expected: Forward a new client message to start a fresh booking. While on "enter row number" step (first row entry, not from menu), send /Отмена. Bot clears to IDLE with "Операция отменена. Состояние сброшено."
result: pass

### 5. /cancel in context switch confirmation
expected: While working with client A, forward a message from client B. Bot asks "Переключиться?". Send /Отмена. Bot says "Продолжаем работу с [client A name]" and restores previous state — you can continue where you left off with client A.
result: pass

### 6. /exit from any active state
expected: While in any active operation (e.g., entering row or seats), send /Выход. Bot replies "Сессия завершена. Состояние сброшено." and fully resets to IDLE — different from /cancel which goes back one step.
result: pass

### 7. Row with no free seats during booking
expected: During booking, enter a row number where all seats are occupied. Bot replies "Ряд X: нет свободных мест. Введите другой ряд:" and stays on row input — does NOT advance to seat input.
result: pass

### 8. Row with no booked seats during deletion
expected: During seat deletion, enter a row number where the current booking has no seats. Bot replies "Ряд X: в этой брони нет мест для удаления. Введите другой ряд:" and stays on row input.
result: pass

### 9. Row with no free seats during reserve add
expected: As admin in /Резерв → add reserve flow, enter a row where all seats are occupied. Bot replies "Ряд X: нет свободных мест. Введите другой ряд:" and stays on row input.
result: pass

### 10. Row with no reserved seats during reserve remove
expected: As admin in /Резерв → remove reserve flow, enter a row with no reserved seats. Bot replies "Ряд X: нет зарезервированных мест. Введите другой ряд:" and stays on row input.
result: pass

## Summary

total: 10
passed: 10
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]

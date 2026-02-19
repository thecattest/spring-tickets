---
phase: 11
plan: 03
subsystem: bot-handlers
tags: [dead-code-removal, steps-integration, constants, texts]

dependency-graph:
  requires:
    - 09-steps (handle_row_input, handle_seat_input, handle_confirmation)
    - 09-foundation (Btn constants, texts.py)
    - 10-router (Router owns all registrations; register_handlers is dead)
  provides:
    - Migrated bot/handlers/reserve.py with no dead code
  affects:
    - 11-08 (cleanup verification pass reads reserve.py)

tech-stack:
  added: []
  patterns:
    - lazy-imports-in-handler-body (from bot.steps import handle_row_input inside function)
    - steps-py-validation (handle_row_input / handle_seat_input / handle_confirmation)
    - btn-constants (Btn.ADD, Btn.DELETE replacing raw strings)
    - texts-constants (texts.ERR_* / texts.PROMPT_* / texts.MSG_* replacing inline strings)

file-tracking:
  created: []
  modified:
    - bot/handlers/reserve.py

decisions:
  - id: keep-seatoccupiederror-inline
    choice: SeatOccupiedError conflict message building kept inline in reserve_comment_handler
    rationale: Conflict detail is dynamically assembled per-seat; too dynamic for texts.py static constant
    alternatives: [move-to-texts-py]
  - id: reserve-seat-validation-layout-only
    choice: handle_seat_input(mode="layout_only") for both adding and removing seats
    rationale: Reserves can overlap bookings; db.add_reserve handles conflicts. Removal only needs layout check; db.release_reserve handles business logic.
    alternatives: [availability-mode, membership-mode]

metrics:
  duration: ~2 min
  completed: 2026-02-19
---

# Phase 11 Plan 03: Reserve.py Migration Summary

**One-liner:** Removed 8 closure wrappers, dead command dispatch block, and Bot import from reserve.py; wired handle_row_input/handle_seat_input/handle_confirmation from steps.py and Btn/texts constants throughout.

## What Was Done

Migrated `bot/handlers/reserve.py` as the largest single-file migration in Phase 11 (8 closures removed). The file previously contained a `register_handlers(bot)` function with 8 inner closure wrappers that are dead code since Phase 10's Router took over all handler registration. It also had a dead command dispatch block (`elif text.startswith("/"):`) in `reserve_action_handler` that was superseded by the Router intercepting commands before state handlers fire.

### Changes Made

**Removed:**
- `register_handlers(bot)` function (lines 383-430) and all 8 inner closure wrappers:
  - `reserve_command_with_storage`
  - `reserve_action_with_storage`
  - `reserve_adding_row_with_storage`
  - `reserve_adding_seats_with_storage`
  - `reserve_comment_with_storage`
  - `reserve_removing_row_with_storage`
  - `reserve_removing_seats_with_storage`
  - `reserve_remove_confirm_with_storage`
- Dead command dispatch block in `reserve_action_handler` (lines 83-100): the `elif text.startswith("/"):` block manually re-dispatching to other handlers
- `from vkbottle.bot import Bot` (unused after register_handlers removed)
- `from bot.utils.seat_parser import parse_seats, SeatParseError` (replaced by steps.py)
- `from bot.utils.layout import is_valid_row, is_valid_seat, get_seat_count, get_row_range` (replaced by steps.py; `get_seat_count` kept for seat prompt formatting)

**Added (module-level imports):**
- `from bot.constants import Btn`
- `from bot import texts`

**Wired (lazy imports inside handler bodies per circular-import-safe pattern):**
- `from bot.steps import handle_row_input` — used in `reserve_adding_row_handler` and `reserve_removing_row_handler`
- `from bot.steps import handle_seat_input` — used in `reserve_adding_seats_handler` and `reserve_removing_seats_handler` (both with `mode="layout_only"`)
- `from bot.steps import handle_confirmation` — used in `reserve_remove_confirm_handler`

**Replaced:**
- `text == "Добавить"` → `text == Btn.ADD` in `reserve_action_handler`
- `text == "Удалить"` → `text == Btn.DELETE` in `reserve_action_handler`
- Inline row validation (8-line try/int/is_valid_row pattern) → `handle_row_input()` call in both row handlers
- Inline seat parse/layout validation → `handle_seat_input(mode="layout_only")` in both seat handlers
- `if text == "Подтвердить" / elif text == "Отмена"` → `handle_confirmation()` in confirm handler
- Inline message strings replaced with `texts.*` constants:
  - `"Управление резервами доступно только администраторам."` → `texts.ERR_RESERVE_ADMIN_ONLY`
  - `"Ошибка: ваш аккаунт не найден в системе."` → `texts.ERR_ACCOUNT_NOT_FOUND`
  - `"Введите номер ряда:"` → `texts.PROMPT_ENTER_ROW`
  - `"Выберите действие:"` → `texts.PROMPT_SELECT_ACTION`
  - `f"...Управление резервами:"` → `texts.MSG_RESERVE_ACTION_HEADER.format(...)`
  - `f"Введите номера мест для резерва ..."` → `texts.MSG_ENTER_SEATS_RESERVE.format(...)`
  - `f"Введите номера мест для снятия резерва ..."` → `texts.MSG_ENTER_SEATS_UNRESERVE.format(...)`
  - `"Введите комментарий для резерва:"` → `texts.PROMPT_ENTER_COMMENT`
  - `"Комментарий обязателен. Введите комментарий:"` → `texts.PROMPT_COMMENT_REQUIRED`
  - `f"Резерв создан:..."` → `texts.MSG_RESERVE_CREATED.format(...)`
  - `f"Ошибка при создании резерва: {e}"` → `texts.ERR_RESERVE_CREATE.format(error=e)`
  - `"Ошибка: потерян контекст. Начните заново с /Резерв."` → `texts.ERR_CONTEXT_LOST_RESERVE` (multiple places)
  - `f"Снять резерв:\nРяд {row}: {seats_str}\n\nПодтвердить?"` → `texts.MSG_CONFIRM_UNRESERVE.format(...)`
  - `f"Ошибка при снятии резерва: {e}"` → `texts.ERR_RESERVE_REMOVE.format(error=e)`
  - `"Отменено."` → `texts.MSG_CANCELLED_BRIEF`

**Kept inline (too dynamic for texts.py):**
- `SeatOccupiedError` conflict detail messages in `reserve_comment_handler` (per-seat detail assembles dynamically from conflict data)
- "Резерв снят: Ряд..." result text and previous notes display (builds dynamically from DB results)

**Unchanged:**
- All 8 handler signatures: `(message: Message, storage: RedisStorage)` — required by Router
- Business logic of all handlers
- `get_seat_count` import kept (used for seat-count display in row handler prompts)

## Decisions Made

1. **SeatOccupiedError messages kept inline**: The conflict detail in `reserve_comment_handler` builds per-seat info from `c['status']`, `c['note']`, `c['reservation_id']`, and `db.get_reservation_seats()`. This is too dynamic for a static texts.py constant. Per prior decision from Phase 9.

2. **mode="layout_only" for both adding and removing seat handlers**: Reserve-adding only needs layout validation because `db.add_reserve()` catches conflicts itself (SeatOccupiedError). Reserve-removing only needs layout validation because `db.release_reserve()` handles the business logic of finding the reserved seats.

## Verification Results

All 4 verification checks passed:
- `python3 -c "from bot.handlers.reserve import ..."` — success, no errors
- `grep -n "register_handlers" bot/handlers/reserve.py` — empty (PASS)
- `grep -n 'text.startswith("/")' bot/handlers/reserve.py` — empty (PASS)
- `grep -n "from vkbottle.bot import Bot" bot/handlers/reserve.py` — empty (PASS)

## Deviations from Plan

None — plan executed exactly as written. The `get_seat_count` import was retained (plan listed it for possible removal) because it is still used in `reserve_adding_row_handler` and `reserve_removing_row_handler` for the seat-count display in prompts. This is correct behavior; steps.py does not expose seat_count in its return value.

## Next Phase Readiness

- `reserve.py` is fully migrated; no dead code remains
- Ready for Phase 11 plans 04-08 (commands.py, menu.py, payment.py, debtors.py, cleanup)
- Phase 11-08 cleanup verification pass will confirm `grep -r "register_handlers" bot/` returns empty across all files

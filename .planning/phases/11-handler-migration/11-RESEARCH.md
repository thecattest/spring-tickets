# Phase 11: Handler Migration - Research

**Researched:** 2026-02-19
**Domain:** Dead-code removal from handler files after Router migration; wiring texts.py, steps.py, Btn/Cmd constants into handler bodies
**Confidence:** HIGH

## Summary

Phase 10 is fully complete: `bot/router.py` owns all handler registrations via `BotLabeler`, `bot/main.py` already uses `bot.labeler.load(router.labeler)`, and `_with_auth_guard()` injects storage into all state handlers. The old `register_handlers()` functions and closure wrappers in each handler file are now pure dead code — they are never called.

Phase 11 is a dead-code removal and refactoring pass. Each handler file needs three things removed or replaced:
1. The `register_handlers(bot)` function at the bottom (dead — router owns registration)
2. The inner closure wrappers (`async def xxx_with_storage(message)`) inside those functions (dead)
3. The manual command dispatch `elif text.startswith("/"):` blocks in `menu.py` and `reserve.py` (dead — router intercepts commands before state handlers fire)

Additionally, Phase 11 wires in three previously-built but unwired assets:
- `bot/texts.py` — 62 string constants (Phase 9 deliverable, noted as "wired in Phase 11")
- `bot/steps.py` — `handle_row_input()`, `handle_seat_input()`, `handle_confirmation()` shared validators
- `bot/constants.py` — `Btn` and `Cmd` StrEnum members for text comparisons

The existing handler logic (the actual bot flows) is NOT changed — only the registration scaffolding and inline string/validation duplication are removed.

**Primary recommendation:** Migrate each handler file atomically (one commit per file). The migration is mechanical: delete `register_handlers()` + closures, replace inline validation with `steps.py` calls, replace inline strings with `texts.py` constants, replace string literals in comparisons with `Btn.*`/`Cmd.*` members.

## Current State Analysis

### What Phase 10 Already Did (DO NOT RE-DO)

The following is already in place in the live codebase:

- `bot/router.py` — complete, with `_wrap()`, `_with_auth_guard()`, `register_all()`
- `bot/main.py` — already uses `Router(redis_storage).register_all()` + `bot.labeler.load(router.labeler)`. Zero `register_handlers()` calls exist in main.py
- `bot/fsm/config.py` — FSM_CONFIG with 18 states and auth_guard per state
- `bot/steps.py` — `handle_row_input()`, `handle_seat_input()`, `handle_confirmation()` implemented but not yet imported by handlers
- `bot/texts.py` — 62 string constants defined but not yet imported by handlers
- `bot/constants.py` — `Btn` and `Cmd` StrEnums defined but not yet imported by handlers

### What Still Has Dead Code

All 7 handler files have `register_handlers(bot)` functions and inner closure wrappers that are never called. Specifically:

| File | register_handlers() lines | Closures count | Other dead code |
|------|--------------------------|---------------|-----------------|
| `reservation.py` | Lines 533-564 | 4 closures | None |
| `deletion.py` | Lines 339-368 | 4 closures | None |
| `reserve.py` | Lines 383-430 | 8 closures | `elif text.startswith("/"):` in `reserve_action_handler` (lines 83-100) |
| `commands.py` | Lines 144-163 | 1 closure | None |
| `menu.py` | Lines 343-364 | 2 closures | `elif text.startswith("/"):` in `main_menu_handler` (lines 177-194) |
| `payment.py` | Lines 253-267 | 1 closure | None |
| `debtors.py` | Lines 89-102 | 0 closures | None (already stateless) |

### Handler Signature Inventory

Understanding which handlers accept `(message, storage)` vs `(message,)` is critical for knowing what the Router wraps:

**Handlers wrapped by Router via `_wrap()` or `_with_auth_guard()` (signature: message + storage):**
- `forwarded_message_handler(message, storage)` — reservation.py
- `awaiting_row_handler(message, storage)` — reservation.py
- `awaiting_seats_handler(message, storage)` — reservation.py
- `seat_addition_menu_handler(message, storage)` — reservation.py
- `main_menu_handler(message, storage)` — menu.py
- `context_switch_handler(message, storage)` — menu.py
- `deleting_row_handler(message, storage)` — deletion.py
- `deleting_seats_handler(message, storage)` — deletion.py
- `deletion_confirm_handler(message, storage)` — deletion.py
- `cancel_confirm_handler(message, storage)` — deletion.py
- `payment_quantity_handler(message, storage)` — payment.py
- `reserve_command_handler(message, storage)` — reserve.py
- `reserve_action_handler(message, storage)` — reserve.py
- `reserve_adding_row_handler(message, storage)` — reserve.py
- `reserve_adding_seats_handler(message, storage)` — reserve.py
- `reserve_comment_handler(message, storage)` — reserve.py
- `reserve_removing_row_handler(message, storage)` — reserve.py
- `reserve_removing_seats_handler(message, storage)` — reserve.py
- `reserve_remove_confirm_handler(message, storage)` — reserve.py
- `cancel_handler(message, storage)` — commands.py
- `exit_handler(message, storage)` — commands.py

**Handlers registered DIRECTLY by Router (no wrap, signature: message only):**
- `start_handler(message)` — commands.py
- `help_handler(message)` — commands.py
- `debtors_command_handler(message)` — debtors.py
- `refresh_debtors_handler(message)` — debtors.py

**These signatures must NOT change during Phase 11 migration** — the Router calls them.

## Standard Stack

### Core (already installed)
| Module | Version | Purpose | Why Standard |
|--------|---------|---------|--------------|
| `bot/texts.py` | Phase 9 | 62 string constants replacing inline literals | Already built, Phase 11 wires it |
| `bot/steps.py` | Phase 9 | Shared validation: `handle_row_input`, `handle_seat_input`, `handle_confirmation` | Already built, Phase 11 wires it |
| `bot/constants.py` | Phase 9 | `Btn` and `Cmd` StrEnums for button/command string comparisons | Already built, Phase 11 wires it |
| `bot/router.py` | Phase 10 | Owns all handler registrations — Phase 11 must not duplicate | Already complete |

### Supporting
| Module | Purpose | Note |
|--------|---------|------|
| `vkbottle.bot.Bot` | No longer imported by handler files | Remove from imports when removing `register_handlers()` |
| `bot.fsm.storage.RedisStorage` | Type annotation for `storage` param | Keep — handlers still accept storage as param |

### Imports to Remove From Each Handler File

When `register_handlers(bot)` is deleted, the `Bot` import becomes unused. Remove it:

```python
# BEFORE (has Bot import for register_handlers)
from vkbottle.bot import Bot, Message

# AFTER (Bot removed, Message kept for type hints)
from vkbottle.bot import Message
```

### New Imports to Add

Each handler file needs to import from the newly-wired modules:

```python
# Add to files that use button comparisons
from bot.constants import Btn, Cmd

# Add to files that have string messages (most files)
from bot import texts

# Add to files with row/seat validation
from bot.steps import handle_row_input, handle_seat_input, handle_confirmation
```

## Architecture Patterns

### Pattern 1: Atomic Per-File Migration

Each handler file is migrated in isolation as one atomic commit:

```
atomic commit for each file =
  1. Remove register_handlers() function and all its inner closures
  2. Remove Bot import (now unused)
  3. Add Btn/Cmd/texts/steps imports as needed
  4. Replace inline validation with steps.py calls
  5. Replace string literals with texts.py constants
  6. Replace string comparisons with Btn.* members
  7. Remove dead elif text.startswith("/") dispatch blocks (menu.py, reserve.py only)
```

No cross-file changes in one commit. The Router already handles all registration — removing `register_handlers()` from any file has zero runtime effect.

### Pattern 2: steps.py Integration for Row Handlers

The three row-input handlers (`awaiting_row_handler`, `deleting_row_handler`, `reserve_adding_row_handler`, `reserve_removing_row_handler`) all contain identical validation. Replace with `handle_row_input()`:

```python
# BEFORE (inline validation, 8 lines)
try:
    row = int(text)
except ValueError:
    min_row, max_row = get_row_range()
    await message.answer(
        f"Неверный формат. Введите номер ряда ({min_row}-{max_row}):"
    )
    return

if not is_valid_row(row):
    min_row, max_row = get_row_range()
    await message.answer(
        f"Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"
    )
    return

# AFTER (steps.py call, 4 lines)
from bot.steps import handle_row_input

result = handle_row_input(text)
if not result.ok:
    await message.answer(result.error_text)
    return
row = result.row
```

### Pattern 3: steps.py Integration for Seat Handlers

Seat input handlers have three modes. Match the mode to the handler:

| Handler | Mode | What It Validates |
|---------|------|-------------------|
| `awaiting_seats_handler` | `"availability"` | Parse + layout + no other booking |
| `reserve_adding_seats_handler` | `"layout_only"` | Parse + layout (no availability check for reserves) |
| `reserve_removing_seats_handler` | `"layout_only"` | Parse + layout only |
| `deleting_seats_handler` | custom | Parse + layout + membership (uses `"membership"` mode) |

```python
# BEFORE (inline, 20+ lines for availability check)
try:
    seats = parse_seats(text)
except SeatParseError as e:
    await message.answer(f"Ошибка ввода: {e}\n\nПопробуйте снова:")
    return

seat_count = get_seat_count(row)
invalid_seats = [s for s in seats if not is_valid_seat(row, s)]
if invalid_seats:
    ...

# AFTER (steps.py call)
from bot.steps import handle_seat_input

result = handle_seat_input(text, row=row, mode="availability")
if not result.ok:
    await message.answer(result.error_text)
    return
seats = result.seats
```

**IMPORTANT for `deleting_seats_handler`:** The current inline validation in `deletion.py` checks membership (seats belonging to the reservation) and paid status. `handle_seat_input(mode="membership")` covers both cases. Use it.

**IMPORTANT for `awaiting_seats_handler`:** After steps.py validates availability at the individual seat level, the handler still calls `db.add_seats_to_reservation()` which raises `SeatOccupiedError` — a race condition guard. Keep that try/except block unchanged.

### Pattern 4: steps.py Integration for Confirmation Handlers

`handle_confirmation()` in steps.py compares against `Btn.CONFIRM` and `Btn.CANCEL`. It returns `True`, `False`, or `None`. Replace the if/elif chains:

```python
# BEFORE
if text == "Подтвердить":
    # do confirm
elif text == "Отмена":
    # do cancel
else:
    await message.answer("Выберите действие:", keyboard=confirmation_keyboard())

# AFTER
from bot.steps import handle_confirmation

confirmed = handle_confirmation(text)
if confirmed is True:
    # do confirm
elif confirmed is False:
    # do cancel
else:
    await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
```

Applicable to: `deletion_confirm_handler`, `cancel_confirm_handler`, `reserve_remove_confirm_handler`.

### Pattern 5: Btn/Cmd Constants for Text Comparisons

All `if text == "..."` comparisons involving button labels or commands use `Btn.*`:

```python
# BEFORE
if text == "Добавить еще":
    ...
elif text == "Готово":
    ...

# AFTER
from bot.constants import Btn

if text == Btn.ADD_MORE:
    ...
elif text == Btn.DONE:
    ...
```

Similarly for context_switch: `text == "Да"` → `text == Btn.YES`, `text == "Нет"` → `text == Btn.NO`.

### Pattern 6: texts.py for Message Constants

Replace all inline message strings with `texts.*` constants:

```python
# BEFORE
await message.answer("Ошибка: потерян контекст. Начните заново.")

# AFTER
from bot import texts
await message.answer(texts.ERR_CONTEXT_LOST)
```

For parameterized messages:
```python
# BEFORE
await message.answer(f"Добавлено {len(seats)} мест:\nРяд {row}, места: {', '.join(map(str, seats))}\n\nВсего в брони: {total_count} мест")

# AFTER
await message.answer(texts.MSG_SEATS_ADDED.format(
    count=len(seats),
    row=row,
    seats=", ".join(map(str, seats)),
    total=total_count,
))
```

### Pattern 7: Removing Dead Command Dispatch Blocks

`menu.py:main_menu_handler` and `reserve.py:reserve_action_handler` both have `elif text.startswith("/"):` blocks that manually dispatch commands. These are dead code since Phase 10 (Router intercepts commands before state handlers fire).

```python
# REMOVE THIS BLOCK from main_menu_handler in menu.py (lines 177-194):
elif text.startswith("/"):
    # Command entered — clear state and dispatch to command handler
    await storage.delete(message.from_id)
    if text in ("/cancel", "/Отмена"):
        from bot.handlers.commands import cancel_handler
        await cancel_handler(message, storage)
    elif text in ("/debtors", "/Должники"):
        ...
    # etc.

# REMOVE THIS BLOCK from reserve_action_handler in reserve.py (lines 83-100):
elif text.startswith("/"):
    # Command entered — clear state and let command handlers process
    await storage.delete(message.from_id)
    if text in ("/cancel", "/Отмена"):
        from bot.handlers.commands import cancel_handler
        ...
    # etc.
```

After removal, the `else:` clause becomes the fallthrough for unknown text (re-show keyboard).

### Per-File Migration Summary

#### 11-01: reservation.py

Remove:
- `register_handlers(bot)` function (lines 533-564, including 4 inner closures)
- `from vkbottle.bot import Bot, Message` → keep only `Message`

Add imports:
- `from bot.constants import Btn`
- `from bot import texts`
- `from bot.steps import handle_row_input, handle_seat_input`

Key replacements:
- `awaiting_row_handler`: replace 8-line inline row validation with `handle_row_input(text)`
- `awaiting_seats_handler`: replace inline parse/validate/availability check with `handle_seat_input(text, row, mode="availability")`; keep `db.add_seats_to_reservation()` race-condition guard
- `seat_addition_menu_handler`: replace `text == "Добавить еще"` with `Btn.ADD_MORE`, `text == "Готово"` with `Btn.DONE`
- Replace inline error strings with `texts.*` constants

Note: `forwarded_message_handler` is complex and largely uses dynamic strings (names, IDs). Replace only the clearly-matching `texts.*` constants.

#### 11-02: deletion.py

Remove:
- `register_handlers(bot)` function (lines 339-368, including 4 inner closures)
- `Bot` import

Add imports:
- `from bot.constants import Btn`
- `from bot import texts`
- `from bot.steps import handle_row_input, handle_seat_input, handle_confirmation`

Key replacements:
- `deleting_row_handler`: replace inline row validation with `handle_row_input(text)`
- `deleting_seats_handler`: replace inline parse/validate/membership check with `handle_seat_input(text, row, mode="membership", reservation_id=reservation_id)`
- `deletion_confirm_handler`: replace `if text == "Подтвердить"` with `handle_confirmation(text)`; replace inline strings with `texts.*`
- `cancel_confirm_handler`: replace `if text == "Подтвердить"` with `handle_confirmation(text)`; replace inline strings with `texts.*`

#### 11-03: reserve.py

Remove:
- `register_handlers(bot)` function (lines 383-430, including 8 inner closures)
- `Bot` import
- Dead command dispatch `elif text.startswith("/"):` block in `reserve_action_handler` (lines 83-100)

Add imports:
- `from bot.constants import Btn`
- `from bot import texts`
- `from bot.steps import handle_row_input, handle_seat_input, handle_confirmation`

Key replacements:
- `reserve_adding_row_handler`: replace inline row validation with `handle_row_input(text)`
- `reserve_removing_row_handler`: replace inline row validation with `handle_row_input(text)`
- `reserve_adding_seats_handler`: replace inline parse/layout with `handle_seat_input(text, row, mode="layout_only")`
- `reserve_removing_seats_handler`: replace inline parse/layout with `handle_seat_input(text, row, mode="layout_only")`
- `reserve_remove_confirm_handler`: replace `if text == "Подтвердить"` with `handle_confirmation(text)`
- `reserve_action_handler`: replace `text == "Добавить"` with `Btn.ADD`, `text == "Удалить"` with `Btn.DELETE`; remove dead command dispatch block

Note: `reserve_adding_seats_handler` has a special case — after `db.add_reserve()` raises `SeatOccupiedError`, it re-prompts seats. The inline error building for conflicts is too dynamic for texts.py (per prior decision). Keep conflict message building inline.

#### 11-04: commands.py

Remove:
- `register_handlers(bot)` function (lines 144-163, including 1 inner closure)
- `Bot` import

Add imports:
- `from bot import texts`

Key replacements:
- `start_handler`: replace inline multiline string with `texts.WELCOME`
- `help_handler`: replace inline multiline string with `texts.HELP`
- `cancel_handler`: replace inline message strings with `texts.MSG_CANCEL_FULL` and `texts.MSG_CANCELLED`

Note: `exit_handler` sends "Сессия завершена" — add this as a constant to texts.py if not already there, or use the inline string if texts.py doesn't have it yet.

**Check before coding:** `texts.py` does not appear to have an `MSG_SESSION_ENDED` constant for exit_handler's "Сессия завершена. Состояние сброшено." message. Add it to texts.py as part of this plan, or keep inline. Research reveals `texts.py` has `MSG_CANCEL_FULL` but no equivalent for the exit message. The planner should decide: add to texts.py or leave inline. Either is defensible.

#### 11-05: menu.py

Remove:
- `register_handlers(bot)` function (lines 343-364, including 2 inner closures)
- `Bot` import
- Dead command dispatch `elif text.startswith("/"):` block in `main_menu_handler` (lines 177-194)

Add imports:
- `from bot.constants import Btn`
- `from bot import texts`

Key replacements:
- `main_menu_handler`: replace `text == "Добавить"` with `Btn.ADD`, `text == "Удалить"` with `Btn.DELETE`, `text == "Удалить все"` with `Btn.DELETE_ALL`, `text == "Оплата"` with `Btn.PAYMENT`
- Replace inline error strings with `texts.*` constants
- `context_switch_handler`: replace `text == "Да"` with `Btn.YES`, `text == "Нет"` with `Btn.NO`

Note: `show_main_menu` is a helper function (not a handler) — it stays unchanged since it's called by other handlers. Do NOT remove it.

#### 11-06: payment.py

Remove:
- `register_handlers(bot)` function (lines 253-267, including 1 inner closure)
- `Bot` import

Add imports:
- `from bot.constants import Btn`
- `from bot import texts`

Key replacements:
- `payment_quantity_handler`: replace `text == "Отмена"` with `Btn.CANCEL`, `text.startswith("Все ")` with `text.startswith(Btn.PAY_ALL_PREFIX)`
- Replace inline error strings with `texts.*` constants

Note: The `start_payment_flow` function is a shared entry point (not a state handler) — it stays unchanged in structure.

#### 11-07: debtors.py

Remove:
- `register_handlers(bot)` function (lines 89-102, including 0 inner closures)
- `Bot` import

Add imports:
- `from bot import texts`

Key replacements:
- `_show_debtors`: replace `"Вы не зарегистрированы в системе."` with `texts.ERR_NOT_REGISTERED`; replace `"Должников нет."` with `texts.MSG_NO_DEBTORS`; replace `"Ошибка при получении списка должников."` with `texts.ERR_DB_GET_DEBTORS`

Note: "Обновить" button handling is in the Router (`refresh_debtors_handler` registered with `text="Обновить"`), not in debtors.py's `register_handlers()`. The `refresh_debtors_handler` function body calls `_show_debtors(message)` — this is correct and stays. No storage needed, no closures.

#### 11-08: Cleanup verification pass

After all 7 files are migrated:
- `grep -r "register_handlers" bot/` should return empty
- `grep -r "def.*with_storage" bot/` should return empty
- `grep -r "from vkbottle.bot import Bot" bot/handlers/` should return empty
- `bot/main.py` should still have zero `register_handlers()` calls (already verified)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Row number validation | Inline try/int/is_valid_row | `handle_row_input(text)` from steps.py | Already implemented; used by all 4 row handlers |
| Seat number validation + availability | Inline parse/layout/availability check | `handle_seat_input(text, row, mode)` from steps.py | Three modes handle all cases; dynamic error messages already implemented |
| Confirmation button handling | `if text == "Подтвердить"/"Отмена"` | `handle_confirmation(text)` from steps.py | Centralizes Btn.CONFIRM/CANCEL comparison; returns True/False/None |
| Button string constants | Inline `"Добавить"`, `"Оплата"` etc. | `Btn.ADD`, `Btn.PAYMENT` from constants.py | StrEnum members ARE the strings; no `.value` needed |
| User-facing message strings | Inline f-strings | `texts.*` constants from texts.py | Single source of truth; format() for parameterized |

**Key insight:** All the "shared infrastructure" was built in Phase 9. Phase 11 is purely wiring that infrastructure into the handlers. Do not rebuild or modify steps.py, texts.py, or constants.py in Phase 11 — use them as-is.

## Common Pitfalls

### Pitfall 1: Changing Handler Signatures
**What goes wrong:** Changing `awaiting_row_handler(message, storage)` to `awaiting_row_handler(message)` (removing storage param) breaks the Router, which wraps the handler expecting a 2-arg function.
**Why it happens:** Steps.py handlers look like they don't need storage, so it's tempting to remove the param.
**How to avoid:** Never touch handler signatures. The Router is the source of truth for what signatures are expected.
**Warning signs:** `TypeError: awaiting_row_handler() takes 1 positional argument but 2 were given` at runtime.

### Pitfall 2: Forgetting show_main_menu Is Not a State Handler
**What goes wrong:** `show_main_menu()` in menu.py is a shared helper function called from multiple handlers. It is NOT registered as a state handler. Do NOT remove it or confuse it with a handler to migrate.
**Why it happens:** It's defined in menu.py alongside handlers.
**How to avoid:** Only delete `register_handlers()` and its inner closures. Leave all async functions that are actual handler implementations.

### Pitfall 3: Breaking the Lazy Imports
**What goes wrong:** Moving `from bot.handlers.payment import start_payment_flow` from inside a function to the module level of reservation.py or menu.py creates a circular import at startup.
**Why it happens:** Module-level imports are natural habit.
**How to avoid:** Keep all cross-handler imports inside function bodies (the existing lazy import pattern). The prior decision explicitly states: "Lazy imports in handle_row_input/handle_seat_input/handle_confirmation — avoids circular imports at module level."

### Pitfall 4: handle_seat_input Mode Mismatch
**What goes wrong:** Using `mode="availability"` for `deleting_seats_handler` (which needs membership check, not availability) or `mode="membership"` for `awaiting_seats_handler` (which needs availability check, not membership).
**Why it happens:** Three modes exist; easy to pick wrong one.
**How to avoid:**
- `awaiting_seats_handler` → `"availability"` (checks that seats are NOT occupied by anyone)
- `deleting_seats_handler` → `"membership"` (checks that seats ARE in this reservation and not paid)
- `reserve_adding_seats_handler` → `"layout_only"` (reserves can overlap with anything — db.add_reserve handles conflicts)
- `reserve_removing_seats_handler` → `"layout_only"` (just parse and validate layout)

### Pitfall 5: Removing Dead Text-Dispatch Blocks and Breaking the else Clause
**What goes wrong:** Removing the `elif text.startswith("/"):` block from `main_menu_handler` leaves an `else` clause that was previously the last branch. If the removal is done improperly (e.g., removing `else:` too), unknown text inputs crash or silently fail.
**Why it happens:** Mechanical text deletion without checking the else.
**How to avoid:** After removing the dead `elif text.startswith("/"):` block, the structure should be:
```python
if text == Btn.ADD:
    ...
elif text == Btn.DELETE:
    ...
elif text == Btn.DELETE_ALL:
    ...
elif text == Btn.PAYMENT:
    ...
else:
    # Unknown text - re-show keyboard
    await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=main_menu_keyboard())
```

### Pitfall 6: texts.py Missing exit_handler Message
**What goes wrong:** `commands.py` `exit_handler` sends "Сессия завершена. Состояние сброшено.\n\nЧтобы начать заново, перешлите сообщение клиента." — this string is NOT in `texts.py` (which has `MSG_CANCEL_FULL` for cancel_handler's equivalent but no `MSG_EXIT_FULL` or similar).
**Why it happens:** The exit_handler was added in Phase 10-03, after texts.py was finalized.
**How to avoid:** For 11-04, either add `MSG_EXIT_FULL` to `texts.py` (preferred — keeps all strings in one place), or keep the inline string in commands.py. Document the decision in the commit message. The planner should include this in the 11-04 plan as an explicit action.

### Pitfall 7: Availability Error Messages in handle_seat_input Are Inline
**What goes wrong:** The dynamic conflict-detail error message in `handle_seat_input(mode="availability")` builds strings inline (e.g., "бронь #5, всего мест: 3"). These are NOT texts.py constants — they're dynamically assembled. The same applies to `SeatOccupiedError` handling in db calls.
**Why it happens:** Trying to replace all strings with texts.py.
**How to avoid:** Per prior decision: "availability mode builds dynamic error message inline — occupancy detail is too dynamic for a static texts.py constant." Accept that the conflict detail messages in steps.py stay inline. Only static/parameterized messages go in texts.py.

### Pitfall 8: Non-Atomic Commits (Multiple Files Per Commit)
**What goes wrong:** Migrating `reservation.py` and `menu.py` in the same commit means if the commit is rolled back, both are reverted instead of one at a time.
**Why it happens:** Temptation to batch.
**How to avoid:** One commit per handler file. The plan has 8 sub-plans: 11-01 through 11-08. Follow this strictly.

## Code Examples

### Removing register_handlers() Pattern

```python
# REMOVE THIS ENTIRE FUNCTION from each handler file:
def register_handlers(bot: Bot):
    """..."""
    storage = bot.state_dispenser

    async def xxx_with_storage(message: Message):
        await xxx_handler(message, storage)

    bot.on.message(state=BotState.XXX)(xxx_with_storage)
    logger.info("XXX handlers registered")
```

### handle_row_input Integration (reservation.py and reserve.py)

```python
# Source: bot/steps.py (verified, lines 32-51)
async def awaiting_row_handler(message: Message, storage: RedisStorage):
    from bot.steps import handle_row_input
    from bot import texts

    result = handle_row_input(message.text)
    if not result.ok:
        await message.answer(result.error_text)
        return
    row = result.row

    # Get existing context to preserve it
    context = await storage.get_context(message.from_id)
    context['current_row'] = row

    seat_count = get_seat_count(row)
    await message.answer(
        texts.MSG_ROW_SEAT_COUNT.format(row=row, seat_count=seat_count)
    )
    await storage.set(message.from_id, BotState.AWAITING_SEATS, **context)
```

### handle_seat_input Integration (awaiting_seats_handler)

```python
# Source: bot/steps.py (verified, lines 54-111)
async def awaiting_seats_handler(message: Message, storage: RedisStorage):
    from bot.steps import handle_seat_input
    from bot import texts

    context = await storage.get_context(message.from_id)
    row = context.get("current_row")
    reservation_id = context.get("reservation_id")

    if not row or not reservation_id:
        await message.answer(texts.ERR_CONTEXT_LOST_FWD)
        await storage.delete(message.from_id)
        return

    result = handle_seat_input(message.text, row=row, mode="availability")
    if not result.ok:
        await message.answer(result.error_text)
        return
    seats = result.seats

    # All seats available - add them (race condition guard kept)
    try:
        seller_id = db.get_seller_id(message.from_id)
        assignments = db.add_seats_to_reservation(reservation_id, row, seats, seller_id)
        all_seats = db.get_reservation_seats(reservation_id)
        total_count = len(all_seats)
        await message.answer(
            texts.MSG_SEATS_ADDED.format(
                count=len(seats),
                row=row,
                seats=", ".join(map(str, seats)),
                total=total_count,
            ),
            keyboard=seat_addition_menu_keyboard()
        )
        await storage.set(message.from_id, BotState.SEAT_ADDITION_MENU, **context)
    except db.SeatOccupiedError as e:
        # Race condition: re-validate inline (dynamic conflict detail)
        error_lines = ["Места уже заняты:"]
        for c in e.conflicts:
            ...  # keep existing inline error building
```

### handle_confirmation Integration

```python
# Source: bot/steps.py (verified, lines 142-149)
async def deletion_confirm_handler(message: Message, storage: RedisStorage):
    from bot.steps import handle_confirmation
    from bot import texts
    from bot.constants import Btn

    context = await storage.get_context(message.from_id)
    # ... extract context ...

    confirmed = handle_confirmation(message.text)
    if confirmed is True:
        # Release seats
        ...
    elif confirmed is False:
        await message.answer(texts.MSG_CANCELLED_BRIEF, keyboard=get_empty_keyboard())
        await show_main_menu(message, storage, reservation_id, buyer_vk_user_id,
                             buyer_display_name, buyer_vk_api_id)
    else:
        await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
```

### Removing Dead Command Dispatch Block (menu.py)

```python
# BEFORE main_menu_handler (lines 177-194 in menu.py):
elif text == "Оплата":
    from bot.handlers.payment import start_payment_flow
    await start_payment_flow(...)

elif text.startswith("/"):                           # DELETE THIS ELIF BLOCK
    await storage.delete(message.from_id)
    if text in ("/cancel", "/Отмена"):
        from bot.handlers.commands import cancel_handler
        await cancel_handler(message, storage)
    elif text in ("/debtors", "/Должники"):
        ...
    # etc.

else:
    await message.answer(
        "Выберите действие:",
        keyboard=main_menu_keyboard()
    )

# AFTER:
elif text == Btn.PAYMENT:
    from bot.handlers.payment import start_payment_flow
    await start_payment_flow(...)

else:
    await message.answer(
        texts.PROMPT_SELECT_ACTION,
        keyboard=main_menu_keyboard()
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Handler files call `bot.on.message()` via `register_handlers(bot)` | Router calls `self.labeler.message()` via `register_all()` | Phase 10 | Handler files no longer need Bot import; dead code removable |
| Storage injected via closure in each handler file | Storage injected by Router via `_wrap()` / `_with_auth_guard()` | Phase 10 | 14 closure wrappers across 7 files become dead code |
| Row/seat validation duplicated in 4+ handlers each | Shared via `handle_row_input()` / `handle_seat_input()` | Phase 9 (built), Phase 11 (wired) | ~60 lines of duplicated validation removed |
| User-facing strings inline in handlers | `texts.py` constants | Phase 9 (built), Phase 11 (wired) | 62 constants replace ~80 inline literals |
| Button comparisons as string literals | `Btn.ADD`, `Btn.CONFIRM`, etc. StrEnum | Phase 9 (built), Phase 11 (wired) | Typo-proof, refactorable |
| Manual command dispatch in MAIN_MENU and RESERVE_ACTION | Router intercepts commands before state handlers | Phase 10 | Dead code in menu.py/reserve.py; removed in Phase 11 |

**Deprecated patterns removed in Phase 11:**
- `register_handlers(bot)` function pattern: replaced by Router, removed from all 7 files
- Closure wrappers (`async def xxx_with_storage`): replaced by `_wrap()` in Router, removed from all 7 files
- Manual `elif text.startswith("/"):` dispatch: replaced by registration order, removed from menu.py and reserve.py

## Open Questions

1. **exit_handler message in texts.py**
   - What we know: `commands.py exit_handler` sends "Сессия завершена. Состояние сброшено.\n\nЧтобы начать заново, перешлите сообщение клиента." This string is not in texts.py.
   - What's unclear: Should plan 11-04 add `MSG_EXIT_FULL` to texts.py first, then use it? Or leave inline?
   - Recommendation: Add to texts.py in the 11-04 plan step before replacing in commands.py. Keeps all strings in one place.

2. **handle_seat_input for reserve_removing_seats_handler**
   - What we know: `reserve_removing_seats_handler` currently validates layout only (parse + is_valid_seat check). It does NOT check if the seats are actually reserved. That check is implicit in `db.release_reserve()`. `handle_seat_input(mode="layout_only")` matches this.
   - What's unclear: Should we add a membership/availability check before calling `db.release_reserve()`?
   - Recommendation: Keep `"layout_only"` — same behavior as current code. DB error handling is already in place if seats aren't reserved. No behavior change.

3. **SeatOccupiedError conflict messages**
   - What we know: The per-seat conflict detail ("бронь #5, всего мест: 3") is dynamic. It exists in both `awaiting_seats_handler` and `reserve_comment_handler` (via `db.add_reserve`).
   - What's unclear: Should this dynamic message be moved to steps.py's `handle_seat_input(mode="availability")`?
   - Recommendation: No. For `awaiting_seats_handler`, the `db.add_seats_to_reservation()` race condition guard has its own `SeatOccupiedError` catch that is separate from steps.py's pre-validation. Keep both. The steps.py error already handles the pre-DB availability check. The post-DB `SeatOccupiedError` block stays inline.

## Sources

### Primary (HIGH confidence)
- Direct read of `bot/handlers/reservation.py` — complete file, all lines
- Direct read of `bot/handlers/deletion.py` — complete file, all lines
- Direct read of `bot/handlers/reserve.py` — complete file, all lines
- Direct read of `bot/handlers/commands.py` — complete file, all lines
- Direct read of `bot/handlers/menu.py` — complete file, all lines
- Direct read of `bot/handlers/payment.py` — complete file, all lines
- Direct read of `bot/handlers/debtors.py` — complete file, all lines
- Direct read of `bot/router.py` — complete file, all lines (Phase 10 output, verified by 10-VERIFICATION.md)
- Direct read of `bot/main.py` — complete file, confirmed zero register_handlers() calls
- Direct read of `bot/steps.py` — complete file, all lines (Phase 9 output)
- Direct read of `bot/texts.py` — complete file, all lines (Phase 9 output)
- Direct read of `bot/constants.py` — complete file, all lines (Phase 9 output)
- Direct read of `bot/fsm/config.py` — complete file (FSM_CONFIG, 18 states)
- `.planning/phases/10-router/10-VERIFICATION.md` — confirmed Phase 10 passed 4/4 must-haves

### Secondary (MEDIUM confidence)
- N/A — all findings from direct codebase inspection

### Tertiary (LOW confidence)
- N/A

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified from direct codebase reads
- Architecture: HIGH — patterns derived directly from existing Phase 9/10 artifacts
- Pitfalls: HIGH — identified from cross-referencing handler files with router.py and steps.py
- Per-file migration: HIGH — line numbers verified by reading each file

**Research date:** 2026-02-19
**Valid until:** Stable — code does not change between research and planning in this workflow; valid until Phase 11 starts executing

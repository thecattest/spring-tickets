# Phase 8: Foundation - Research

**Researched:** 2026-02-19
**Domain:** Python StrEnum, string constants, bot message consolidation
**Confidence:** HIGH

## Summary

Phase 8 introduces a single source of truth for all UI strings in the bot. The three deliverables are: `bot/constants.py` (button labels and commands as StrEnum + ALL_COMMANDS frozenset), `bot/texts.py` (all user-facing prompt and error strings), and an update to `bot/keyboards.py` to use `Btn.*` members instead of raw string literals.

The codebase has been fully audited. There are **16 unique button label strings** in `keyboards.py`, one of which is a dynamic f-string (`f"Все {booked_count}"`). There are **9 commands** used in `text=` registrations across handler files. There are **31 unique static strings** and **41 f-string templates** passed to `message.answer()` across all handlers — these are the target for `bot/texts.py`.

Python 3.14 is in use, which means `enum.StrEnum` (available since 3.11) is available natively. Verified that `StrEnum` members behave as plain strings in all relevant contexts: `Text(Btn.ADD)`, `text=` param, `if text == Btn.ADD`, and `text in ALL_COMMANDS`.

**Primary recommendation:** Use `from enum import StrEnum` directly. No third-party packages or compatibility shims needed.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `enum.StrEnum` | stdlib (Python 3.11+) | Button and command constants that ARE strings | Members compare equal to their string values; no casting needed |
| `enum.Enum` | stdlib | Base for enums where string identity not needed | Used for BotState already |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `frozenset` | stdlib | Immutable set of all command strings | ALL_COMMANDS — used in `text in ALL_COMMANDS` dispatch checks in menu.py and reserve.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `StrEnum` | `str, Enum` mixin | `class Btn(str, Enum)` works in Python < 3.11 but is more verbose; unnecessary since Python 3.14 is in use |
| Module-level constants | `StrEnum` | Plain `BTN_ADD = "Добавить"` would work but loses namespace grouping and IDE enum completions |

**Installation:**
```bash
# No new packages required - all stdlib
```

## Architecture Patterns

### Recommended Project Structure
```
bot/
├── constants.py     # Btn StrEnum, Cmd StrEnum, ALL_COMMANDS frozenset
├── texts.py         # All user-facing message strings (static + .format() templates)
├── keyboards.py     # Updated: imports Btn.*, no raw button strings
├── handlers/        # Updated: import Txt.*, Btn.*, Cmd.* as needed
└── messages.py      # Existing: formatting functions (not changed in this phase)
```

### Pattern 1: StrEnum for Button Labels (Btn)
**What:** All keyboard button label strings as a StrEnum class.
**When to use:** Anywhere a string is passed to `Text(...)` in keyboards.py, or compared via `if text == "..."` in handlers.

```python
# Source: bot/constants.py
from enum import StrEnum

class Btn(StrEnum):
    # commands_keyboard
    CANCEL_CMD    = "/Отмена"
    HELP_CMD      = "/Справка"
    DEBTORS_CMD   = "/Должники"
    RESERVE_CMD   = "/Резерв"
    # main_menu_keyboard
    ADD           = "Добавить"
    DELETE        = "Удалить"
    DELETE_ALL    = "Удалить все"
    PAYMENT       = "Оплата"
    # seat_addition_menu_keyboard
    ADD_MORE      = "Добавить еще"
    DONE          = "Готово"
    # confirmation_keyboard
    CONFIRM       = "Подтвердить"
    CANCEL        = "Отмена"
    # context_switch_keyboard
    YES           = "Да"
    NO            = "Нет"
    # debtors_keyboard
    REFRESH       = "Обновить"
    # payment_quantity_keyboard prefix (dynamic, not a Btn member)
    # "Все {N}" pattern handled separately — see note below
```

**Note on `"Все {N}"` dynamic button:** The `payment_quantity_keyboard()` generates `Text(f"Все {booked_count}")` and `payment.py` checks `text.startswith("Все ")`. This is inherently dynamic. Define a `Btn.PAY_ALL_PREFIX = "Все "` constant so the prefix string is not duplicated.

### Pattern 2: StrEnum for Commands (Cmd)
**What:** All slash commands as a StrEnum class.
**When to use:** In `text=` registrations AND in the inline dispatch blocks in menu.py and reserve.py.

```python
# Source: bot/constants.py
class Cmd(StrEnum):
    START       = "/start"
    HELP        = "/Справка"
    HELP_EN     = "/help"
    CANCEL      = "/Отмена"
    CANCEL_EN   = "/cancel"
    DEBTORS     = "/Должники"
    DEBTORS_EN  = "/debtors"
    RESERVE     = "/Резерв"
    RESERVE_EN  = "/reserve"

ALL_COMMANDS: frozenset[str] = frozenset(Cmd)
```

**Usage in handler registration:**
```python
# Before (handlers/commands.py):
bot.on.message(text=["/help", "/Справка"])(help_handler)

# After:
from bot.constants import Cmd
bot.on.message(text=[Cmd.HELP_EN, Cmd.HELP])(help_handler)
```

**Usage in inline dispatch (menu.py, reserve.py):**
```python
# Before:
if text in ("/cancel", "/Отмена"):
    ...

# After:
from bot.constants import Cmd
if text in (Cmd.CANCEL_EN, Cmd.CANCEL):
    ...
```

**ALL_COMMANDS for startswith check:**
```python
# Before (menu.py, reserve.py):
elif text.startswith("/"):
    ...

# After — remains as startswith for unknown commands, but specific dispatch uses Cmd.*
# ALL_COMMANDS can be used to detect if text is a known command:
if text in ALL_COMMANDS:
    # known command dispatch
```

### Pattern 3: Texts Module (bot/texts.py)
**What:** Module-level constants for all user-facing strings. Static strings are plain string constants. Parameterized strings use `.format()` placeholders.

```python
# Source: bot/texts.py

# Static strings
ERR_CONTEXT_LOST           = "Ошибка: потерян контекст. Начните заново."
ERR_CONTEXT_LOST_FWD       = "Ошибка: потерян контекст. Начните заново с пересылки сообщения."
ERR_CONTEXT_LOST_RESERVE   = "Ошибка: потерян контекст. Начните заново с /Резерв."
ERR_DB_LOAD_BOOKING        = "Ошибка при загрузке брони. Попробуйте позже."
ERR_DB_CHECK_SEATS         = "Ошибка при проверке мест. Попробуйте позже."
ERR_DB_ADD_SEATS           = "Ошибка при добавлении мест. Попробуйте позже или обратитесь к администратору."
ERR_DB_CREATE_BOOKING      = "Ошибка при создании брони. Попробуйте позже или обратитесь к администратору."
ERR_DB_CREATE_BOOKING_SHORT= "Ошибка при создании брони. Попробуйте позже."
ERR_DB_RECORD_PAYMENT      = "Ошибка при регистрации оплаты. Попробуйте позже."
ERR_DB_GET_DEBTORS         = "Ошибка при получении списка должников."
ERR_DB_GENERATE_SCRIPT     = "Ошибка при генерации скрипта. Попробуйте позже."
ERR_NOT_REGISTERED         = "Вы не зарегистрированы в системе."
ERR_ACCOUNT_NOT_FOUND      = "Ошибка: ваш аккаунт не найден в системе."
ERR_RESERVE_ADMIN_ONLY     = "Управление резервами доступно только администраторам."
ERR_ALREADY_WORKING        = "Вы уже работаете с этим клиентом."
ERR_PAID_CANCEL_ADMIN_ONLY = "В брони есть оплаченные места. Отмена доступна только админам."
ERR_NO_SEATS_TO_DELETE     = "В брони нет мест для удаления."
ERR_NO_SEATS               = "В брони нет мест."

PROMPT_ENTER_ROW           = "Введите номер ряда:"
PROMPT_ENTER_ROW_DELETE    = "Введите номер ряда для удаления:"
PROMPT_ENTER_COMMENT       = "Введите комментарий для резерва:"
PROMPT_COMMENT_REQUIRED    = "Комментарий обязателен. Введите комментарий:"
PROMPT_SELECT_ACTION       = "Выберите действие:"
PROMPT_SELECT_QUANTITY     = "Выберите количество мест из предложенных кнопок."
PROMPT_MIN_QUANTITY        = "Количество мест должно быть не менее 1."

MSG_CANCELLED              = "Отменено."
MSG_BOOKING_CANCELLED      = "Бронь отменена."
MSG_OP_CANCELLED           = "Операция отменена."
MSG_OP_CANCELLED_FULL      = "Операция отменена. Состояние сброшено.\n\nЧтобы начать заново, перешлите сообщение клиента."
MSG_NO_DEBTORS             = "Должников нет."

# Parameterized strings (use .format())
MSG_ROW_SEAT_COUNT         = "Ряд {row} (мест: {seat_count}).\n\nВведите номера мест через пробел, запятую или диапазон.\nПримеры: '5 6 7' или '5, 6, 7' или '5-7'"
MSG_ENTER_SEATS_ROW        = "Введите номера мест для удаления (ряд {row}, мест: {seat_count}):"
MSG_ENTER_SEATS_RESERVE    = "Введите номера мест для резерва (ряд {row}, мест: {seat_count}):"
MSG_ENTER_SEATS_UNRESERVE  = "Введите номера мест для снятия резерва (ряд {row}, мест: {seat_count}):"
ERR_INVALID_ROW            = "Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"
ERR_INVALID_ROW_FORMAT     = "Неверный формат. Введите номер ряда ({min_row}-{max_row}):"
ERR_INVALID_SEATS          = "Недопустимые номера мест: {seats}.\nДля ряда {row} доступны места 1-{seat_count}.\n\nВведите другие места:"
ERR_PARSE_INPUT            = "Ошибка ввода: {error}\n\nПопробуйте снова:"
MSG_SEATS_ADDED            = "Добавлено {count} мест:\nРяд {row}, места: {seats}\n\nВсего в брони: {total} мест"
MSG_SEATS_DELETED          = "Удалено {count} мест."
MSG_NO_SEATS_FOR_PAYMENT   = "У клиента {name} нет мест для оплаты. Все места уже оплачены."
ERR_QTY_EXCEEDS            = "Количество мест превышает доступные для оплаты ({available}). Введите количество от 1 до {available}:"
ERR_INSUFFICIENT_SEATS     = "Ошибка: запрошено {requested} мест, но доступно только {available}."
MSG_SWITCH_TO_CLIENT       = "Переключиться на {name}?\nТекущая операция с {current} будет отменена."
MSG_SWITCH_RECEIPT         = "Получен чек от {name}.\nПереключиться с {current} на {name}?"
MSG_SWITCH_PLAIN           = "Вы работаете с {current}.\nПереключиться на {name}?"
MSG_CONTINUE_WITH          = "Продолжаем работу с {name}."
MSG_NEW_BOOKING_NO_RES     = "У {name} нет активной брони.\nСоздана новая бронь (ID: {id}).\n\nВведите номер ряда:"
MSG_NEW_BOOKING_CREATED    = "Создана новая бронь для {name} (ID: {id}).\n\nВведите номер ряда:"
MSG_CONFIRM_DELETE_SEATS   = "Удалить места:\nРяд {row}: {seats}\n"
MSG_CONFIRM_UNRESERVE      = "Снять резерв:\nРяд {row}: {seats}\n\nПодтвердить?"
MSG_RESERVE_CREATED        = "Резерв создан:\nРяд {row}, места: {seats}\nКомментарий: {comment}"
MSG_RESERVE_ACTION_HEADER  = "{reserves}\n\nУправление резервами:"
ERR_DELETE_SEATS           = "Ошибка при удалении мест: {error}"
ERR_CANCEL_BOOKING         = "Ошибка при отмене брони: {error}"
ERR_RESERVE_CREATE         = "Ошибка при создании резерва: {error}"
ERR_RESERVE_REMOVE         = "Ошибка при снятии резерва: {error}"
MSG_SEATS_NOT_IN_BOOKING   = "Места не принадлежат данной брони: {seats}.\n\nВведите другие места:"
MSG_SEATS_ALREADY_PAID     = "Места уже оплачены, удалить нельзя: {seats}.\n\nВведите другие места:"
```

### Pattern 4: keyboards.py using Btn.*
**What:** All `Text(...)` calls use `Btn.*` enum members instead of raw strings.

```python
# Before (keyboards.py):
from vkbottle import Keyboard, KeyboardButtonColor, Text

keyboard.add(Text("Добавить"), color=KeyboardButtonColor.PRIMARY)

# After:
from vkbottle import Keyboard, KeyboardButtonColor, Text
from bot.constants import Btn

keyboard.add(Text(Btn.ADD), color=KeyboardButtonColor.PRIMARY)
```

**Dynamic button is the exception:** `Text(f"Все {booked_count}")` stays as-is since it is parameterized. The `"Все "` prefix string moves to `Btn.PAY_ALL_PREFIX`.

### Anti-Patterns to Avoid
- **Mixing Btn.* and raw strings for the same button:** If `keyboards.py` uses `Btn.ADD` but a handler still checks `if text == "Добавить"`, the refactor is incomplete. Both sides must use the same constant.
- **Putting formatting functions in texts.py:** `messages.py` already holds multi-line formatting functions. `texts.py` is for short prompt/error strings only.
- **Making Cmd contain only Russian variants:** Both Russian and English variants of commands are in use (`/cancel` and `/Отмена`). Both must be in `Cmd` so `ALL_COMMANDS` is complete.
- **Changing messages.py in this phase:** Phase 8 scope does NOT include refactoring `messages.py`. The complex f-string templates in that file (reservation scripts, payment confirmations) are out of scope.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| String constants that compare == to plain strings | Custom `__eq__` override | `StrEnum` | Built-in, stdlib, zero overhead |
| Set membership test for all commands | Manual list | `frozenset(Cmd)` | O(1) lookup, auto-derived from enum |

**Key insight:** `StrEnum` means no `.value` access needed anywhere. `Btn.ADD == "Добавить"` is `True`. `if text == Btn.ADD` works without change. No migration of comparison logic is needed in handlers — only the string literal needs replacing.

## Common Pitfalls

### Pitfall 1: texts.py scope creep
**What goes wrong:** Including multi-line script generation templates (like reservation scripts, payment confirmations) in `texts.py`.
**Why it happens:** These are also user-facing strings and technically "text".
**How to avoid:** The boundary is: `messages.py` has FUNCTIONS that BUILD multi-line formatted content. `texts.py` has MODULE-LEVEL CONSTANTS for short single-purpose strings (prompts, errors). No functions in `texts.py`.
**Warning signs:** If `texts.py` starts importing `SeatAssignment` or `Decimal`, scope has crept into `messages.py` territory.

### Pitfall 2: Forgetting inline command dispatch strings
**What goes wrong:** Updating `text=` registrations in `register_handlers()` but missing the `if text in ("/cancel", "/Отмена")` inline dispatch blocks in `menu.py` and `reserve.py`.
**Why it happens:** Two patterns of command string usage coexist: (1) `bot.on.message(text=[...])` registrations and (2) manual `if text in (...)` dispatch inside state handlers.
**How to avoid:** After creating `Cmd`, grep for every string that starts with `/` in handler files. Update both registration and dispatch.
**Warning signs:** Commands work from idle state (registration correct) but fail inside MAIN_MENU or RESERVE_ACTION (dispatch incorrect).

### Pitfall 3: PAY_ALL dynamic button prefix
**What goes wrong:** Marking `"Все "` as a Btn member, then trying to do `if text == Btn.PAY_ALL_PREFIX` — won't match `"Все 29"`.
**Why it happens:** The button label is dynamic (`f"Все {N}"`), but the detection uses `text.startswith("Все ")`.
**How to avoid:** Define `Btn.PAY_ALL_PREFIX = "Все "` (with trailing space). Keep detection as `text.startswith(Btn.PAY_ALL_PREFIX)`. Never generate `Text(Btn.PAY_ALL_PREFIX)` — that stays as `Text(f"Все {booked_count}")`.

### Pitfall 4: texts.py constants that duplicate messages.py strings
**What goes wrong:** Adding `MSG_SEAT_STATUS` constants to `texts.py` that duplicate partial strings inside `messages.py` formatting functions.
**Why it happens:** `messages.py` has many embedded Russian strings inside formatting functions (e.g., `"📌Бронь"`, `"Нет мест"`, `"Активных резервов нет."`).
**How to avoid:** Phase 8 TEXT-01 requirement is to consolidate strings from handlers — not from `messages.py`. Leave `messages.py` as-is.

### Pitfall 5: start command not in Cmd enum
**What goes wrong:** `/start` is used in `bot.on.message(text="/start")` and in inline dispatch but differs from the Russian commands — it has no Russian variant.
**Why it happens:** Most commands have both English and Russian variants, but `/start` is command-only.
**How to avoid:** Include `Cmd.START = "/start"` in the enum.

## Code Examples

Verified patterns from codebase audit:

### StrEnum works transparently with vkbottle Text()
```python
# Verified with Python 3.14 + vkbottle installed
from enum import StrEnum
from vkbottle import Keyboard, Text, KeyboardButtonColor

class Btn(StrEnum):
    ADD = "Добавить"

kb = Keyboard(inline=True)
kb.add(Text(Btn.ADD), color=KeyboardButtonColor.PRIMARY)
# Output: {"buttons": [[{"action": {"label": "Добавить", ...}}]]}
```

### StrEnum equality works for if text == comparisons
```python
from enum import StrEnum

class Btn(StrEnum):
    CONFIRM = "Подтвердить"
    CANCEL  = "Отмена"

text = "Подтвердить"
if text == Btn.CONFIRM:   # True
    ...
elif text == Btn.CANCEL:  # False
    ...
```

### frozenset derived from Cmd enum
```python
from enum import StrEnum

class Cmd(StrEnum):
    CANCEL    = "/Отмена"
    CANCEL_EN = "/cancel"
    HELP      = "/Справка"

ALL_COMMANDS = frozenset(Cmd)

"/Отмена" in ALL_COMMANDS    # True
"/cancel" in ALL_COMMANDS    # True
"Добавить" in ALL_COMMANDS   # False
```

### texts.py static string usage
```python
# bot/texts.py
ERR_CONTEXT_LOST = "Ошибка: потерян контекст. Начните заново."

# bot/handlers/deletion.py
from bot.texts import ERR_CONTEXT_LOST

await message.answer(ERR_CONTEXT_LOST)
```

### texts.py parameterized string usage
```python
# bot/texts.py
ERR_INVALID_ROW = "Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"

# bot/handlers/reservation.py
from bot.texts import ERR_INVALID_ROW

await message.answer(ERR_INVALID_ROW.format(min_row=min_row, max_row=max_row))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw string literals in keyboards.py | `Btn.*` StrEnum | Phase 8 | Typos in button labels become static errors |
| Raw strings in handler registration | `Cmd.*` StrEnum | Phase 8 | Command names are centralized; renaming is one-place |
| Inline message strings in handlers | `bot/texts.py` constants | Phase 8 | All user-visible strings auditable in one file |

**Deprecated/outdated:**
- Raw string literals in `Text(...)` calls: replaced by `Btn.*` after this phase
- Hardcoded command strings in both `text=` params and inline dispatch: replaced by `Cmd.*`

## Open Questions

1. **Scope of texts.py vs messages.py**
   - What we know: `messages.py` has complex formatting FUNCTIONS; `texts.py` should have simple string CONSTANTS
   - What's clear: Phase 8 TEXT-01 says "all user-facing prompt and error message strings" — this means handler-level strings, not the formatter functions in `messages.py`
   - Recommendation: Do NOT touch `messages.py` in this phase. Scope = strings passed directly to `message.answer()` from handlers.

2. **start.py / handlers text strings**
   - What we know: `commands.py` has two long multi-line strings (welcome text, help text) assigned to local `text` variables before being passed to `message.answer()`
   - What's unclear: Whether these count as "prompt strings" for TEXT-01 or are more like template content
   - Recommendation: Include them in `texts.py` since they are user-facing bot prompts (WELCOME, HELP).

## Sources

### Primary (HIGH confidence)
- Direct codebase audit of all 7 handler files, keyboards.py, messages.py
- Python 3.14 stdlib `enum.StrEnum` — verified with `python3 -c "from enum import StrEnum"`
- vkbottle source: `/opt/homebrew/lib/python3.14/site-packages/vkbottle/dispatch/rules/base.py` — TextRule implementation confirmed: uses `event.text in self.texts` (equality check)
- Live execution tests: StrEnum with `Text()`, equality, `in` list, frozenset — all confirmed

### Secondary (MEDIUM confidence)
- N/A — all findings verified from primary sources

### Tertiary (LOW confidence)
- N/A

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — StrEnum is stdlib, verified on installed Python 3.14
- Architecture: HIGH — based on complete codebase audit, vkbottle source read
- Pitfalls: HIGH — identified from code patterns, verified with execution tests

**Research date:** 2026-02-19
**Valid until:** Stable — Python stdlib, no third-party churn

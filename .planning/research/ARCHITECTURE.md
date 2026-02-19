# Architecture Patterns: VK Bot Refactoring

**Domain:** VK bot with multi-state FSM (vkbottle 4.6.2)
**Researched:** 2026-02-19
**Confidence:** HIGH — all findings verified against installed vkbottle 4.6.2 source code

---

## How vkbottle's Handler System Actually Works

Understanding this is prerequisite to everything else. Verified directly from installed source.

### The Dispatch Chain

```
Bot.run_forever()
  └── polling: receives raw VK event dict
        └── Bot.process_event(event)
              └── Bot.router.route(event, api)
                    └── BotMessageView.handle_event(event, ctx_api, state_dispenser)
                          ├── pre_middleware() — runs all view.middlewares
                          ├── for handler in view.handlers:
                          │     result = await handler.filter(message, context_variables)
                          │     if result: handler.handle(message, **context_variables)
                          │     if handler.blocking: break
                          └── post_middleware()
```

### What `bot.on.message(state=BotState.X)(fn)` actually does

`bot.on` is `bot.labeler` (a `BotLabeler`).
`bot.on.message(state=BotState.AWAITING_ROW)` calls `BaseLabeler.message()` with keyword
`state=BotState.AWAITING_ROW`, which gets translated to `StateRule(BotState.AWAITING_ROW)`.

This appends a `FromFuncHandler(fn, StateRule(BotState.AWAITING_ROW))` to
`bot.labeler.message_view.handlers` — a flat list.

**Key fact:** handler order in the list is evaluation order. The first handler whose
`filter()` returns truthy wins (because `blocking=True` by default).

### What `BotLabeler.load(other_labeler)` does

```python
def load(self, labeler: BaseLabeler):
    self.message_view.handlers.extend(labeler.message_view.handlers)
    self.message_view.middlewares.extend(labeler.message_view.middlewares)
    # also extends raw_event_view
```

This is the official way to compose labelers — extend the main labeler's handler list
with another labeler's handlers. This is the correct foundation for `router.py`.

### How state matching works

`StateRule.check()`:
```python
async def check(self, event: BaseMessageMin) -> bool:
    if event.state_peer is None:
        return not self.state  # None state_peer matches state=None handlers
    return event.state_peer.state in self.state
```

`event.state_peer` is a `StatePeer` object fetched from `RedisStorage.get(peer_id)` and
attached to the message before handlers run. The `.state` field is the string representation
of the `BotState` enum value (e.g., `"BotState:awaiting_row"`).

### Command interception problem (root cause of the existing workaround)

Because handlers are evaluated in registration order, and state handlers use `blocking=True`,
a message arriving in `MAIN_MENU` state is consumed by `main_menu_with_storage` before
the `/Отмена` text handler registered in `commands.register_handlers()` can match.

This is why `menu.py` and `reserve.py` both have manual `elif text.startswith("/"):` blocks
that re-dispatch to command handlers — command text handlers lose the race against state
handlers when the user has an active state.

---

## Current Architecture Problems (Concrete)

1. **Storage injection via closure**: Every `register_handlers(bot)` function creates
   closure wrappers to pass `storage` down. 14 such wrappers exist across 7 files.

2. **Command interception duplication**: Command re-dispatch logic copied in `menu.py`
   (lines 177–194) and `reserve.py` (lines 83–100). Adding a new command requires
   touching both files.

3. **Inline messages**: Many strings appear directly in handler bodies, not in `messages.py`.
   Examples: `"Введите номер ряда (1-24):"` in `reservation.py:282`, error strings
   in `deletion.py`, `reserve.py`, etc.

4. **Button string literals**: Keyboard labels like `"Добавить еще"`, `"Подтвердить"`,
   `"Да"` appear as raw strings in both keyboard builders and handler `if text ==` branches.
   Typo in one location silently breaks the handler.

5. **Row input logic duplicated three times**: `awaiting_row_handler`, `deleting_row_handler`,
   `reserve_adding_row_handler`, and `reserve_removing_row_handler` all contain identical
   `try: int(text); if not is_valid_row(row):` blocks with slightly different error messages.

6. **Seat input logic duplicated three times**: `awaiting_seats_handler`,
   `deleting_seats_handler`, `reserve_adding_seats_handler`, `reserve_removing_seats_handler`
   all repeat parse + validate + check-availability logic.

---

## New Component Design

### Component 1: `bot/constants.py`

**Purpose:** Single source of truth for all string literals used in both keyboard builders
and handler `if text ==` comparisons.

**Dependencies:** None (pure constants, no imports from bot/).

```python
from enum import StrEnum

class Btn(StrEnum):
    # Reservation flow
    ADD_MORE    = "Добавить еще"
    DONE        = "Готово"
    # Main menu
    ADD         = "Добавить"
    DELETE      = "Удалить"
    DELETE_ALL  = "Удалить все"
    PAYMENT     = "Оплата"
    # Confirmation
    CONFIRM     = "Подтвердить"
    CANCEL      = "Отмена"
    # Context switch
    YES         = "Да"
    NO          = "Нет"
    # Debtors
    REFRESH     = "Обновить"

class Cmd(StrEnum):
    START       = "/start"
    HELP_RU     = "/Справка"
    CANCEL_RU   = "/Отмена"
    RESERVE_RU  = "/Резерв"
    DEBTORS_RU  = "/Должники"
```

**Usage in keyboard builders:**
```python
keyboard.add(Text(Btn.ADD_MORE), color=KeyboardButtonColor.PRIMARY)
```

**Usage in handlers:**
```python
if text == Btn.ADD_MORE:
    ...
elif text == Btn.DONE:
    ...
```

StrEnum makes `Btn.ADD_MORE == "Добавить еще"` True, so no cast needed.

### Component 2: `bot/texts.py`

**Purpose:** All user-facing strings that are currently inline in handler files.

**Dependencies:** `bot.config` (for SEAT_PRICE, row range). Optionally imports `bot.constants`
if any text references a Btn/Cmd value.

```python
# texts.py

def row_prompt() -> str:
    from bot.utils.layout import get_row_range
    min_row, max_row = get_row_range()
    return f"Введите номер ряда ({min_row}-{max_row}):"

def row_invalid() -> str:
    from bot.utils.layout import get_row_range
    min_row, max_row = get_row_range()
    return f"Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"

def seats_prompt(row: int, seat_count: int) -> str:
    return (
        f"Ряд {row} (мест: {seat_count}).\n\n"
        f"Введите номера мест через пробел, запятую или диапазон.\n"
        f"Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
    )

ERR_CONTEXT_LOST = "Ошибка: потерян контекст. Начните заново с пересылки сообщения."
ERR_DB           = "Ошибка при обращении к базе данных. Попробуйте позже."
# ... etc
```

**Note:** `texts.py` intentionally does NOT import from `messages.py`. `messages.py` holds
formatters that take model objects (seats, debtors) and return structured text.
`texts.py` holds prompts, errors, and simple one-liner strings.

### Component 3: `bot/router.py`

**Purpose:** Provides `@on_state` and `@on_command` decorators that eliminate the closure
boilerplate and solve the command interception problem systematically.

**Dependencies:** `vkbottle.framework.labeler.BotLabeler`, `bot.fsm.storage.RedisStorage`,
`bot.fsm.states.BotState`, `bot.constants.Cmd`.

**How it integrates with vkbottle:**

`router.py` creates a `BotLabeler` instance. Handlers registered on it are loaded into the
main bot labeler via `bot.labeler.load(router.labeler)` in `main.py`. This is the official
vkbottle composition mechanism — verified in `BaseLabeler.load()` source.

```python
# bot/router.py
from vkbottle.framework.labeler import BotLabeler
from vkbottle.bot import Message
from vkbottle import BaseStateGroup

from bot.fsm.storage import RedisStorage


class Router:
    """
    Thin wrapper over BotLabeler that:
    1. Holds a storage reference for injection into handlers
    2. Provides @on_state and @on_command decorators
    3. Exposes a BotLabeler that can be loaded into the main bot
    """

    def __init__(self, storage: RedisStorage):
        self.storage = storage
        self.labeler = BotLabeler()

    def on_state(self, state: BaseStateGroup):
        """
        Register a state handler. Handler receives (message, storage) automatically.
        """
        def decorator(func):
            async def wrapper(message: Message):
                await func(message, self.storage)
            # Preserve name for debugging
            wrapper.__name__ = func.__name__
            self.labeler.message(state=state)(wrapper)
            return func
        return decorator

    def on_command(self, *texts: str):
        """
        Register a command handler. Works in ANY state because command handlers
        are registered on this labeler with blocking=False, and the command
        middleware runs before state handlers.
        """
        def decorator(func):
            async def wrapper(message: Message):
                await func(message, self.storage)
            wrapper.__name__ = func.__name__
            self.labeler.message(text=list(texts))(wrapper)
            return func
        return decorator

    def on_message(self, **kwargs):
        """
        Generic passthrough for cases like func=lambda msg: bool(msg.fwd_messages).
        """
        def decorator(func):
            async def wrapper(message: Message):
                await func(message, self.storage)
            wrapper.__name__ = func.__name__
            self.labeler.message(**kwargs)(wrapper)
            return func
        return decorator
```

**Command interception — the correct fix:**

The existing problem is handler registration order. The fix has two parts:

1. Register command handlers FIRST in the handler list (before state handlers). In
   `main.py`, load command handlers before loading state-based handlers.

2. Remove the `elif text.startswith("/"):` blocks from `menu.py` and `reserve.py`.

Registration order in `main.py` becomes:
```python
bot.labeler.load(commands_labeler)   # registered first → checked first
bot.labeler.load(reservation_labeler)
bot.labeler.load(menu_labeler)
# etc.
```

Because vkbottle evaluates handlers in list order and stops at the first `blocking=True`
match, command handlers registered first will match `/Отмена` before any state handler.

**Alternative — CommandInterceptorMiddleware:**

A middleware approach also works and is cleaner if commands need to run regardless of state
_even when_ they share text with button labels. The middleware runs before any handler:

```python
# bot/router.py (optional middleware approach)
from vkbottle.dispatch.middlewares import BaseMiddleware
from vkbottle.bot import Message

COMMAND_PREFIXES = ("/",)

class CommandInterceptorMiddleware(BaseMiddleware[Message]):
    """
    Pre-middleware that detects command text and clears FSM state.
    Allows command handlers to fire even when user is in an active state.
    """
    async def pre(self) -> None:
        msg: Message = self.event
        text = (msg.text or "").strip()
        if any(text.startswith(p) for p in COMMAND_PREFIXES):
            # Clear state so state=None handlers (commands) match
            state_peer = msg.state_peer
            if state_peer is not None:
                # Don't actually delete here — let the command handler do it
                # Just override state_peer.state so StateRule("idle") matches
                msg.state_peer = None
```

**Recommendation:** Use registration order (approach 1) for simplicity. The middleware
approach is correct but adds indirection. Only reach for middleware if commands need to
fire from within states that also have text-matching handlers with the same text.

### Component 4: `bot/steps.py`

**Purpose:** Extract the repeated row-input and seat-input patterns into shared step
functions that handle validation and prompt generation, returning control to the caller
for flow-specific state transitions.

**Dependencies:** `bot.fsm.storage.RedisStorage`, `bot.fsm.states.BotState`,
`bot.utils.layout`, `bot.utils.seat_parser`, `bot.texts` (for error messages),
`bot.keyboards` (for prompts). Does NOT import from any handler file.

**Design: return-value protocol (not callbacks)**

Steps return a typed result indicating whether input was valid and what the parsed value is.
The handler decides what state to transition to on success. This keeps steps testable in
isolation.

```python
# bot/steps.py
from dataclasses import dataclass
from typing import Optional, List
from vkbottle.bot import Message

from bot.fsm.storage import RedisStorage
from bot.utils.layout import is_valid_row, get_seat_count, get_row_range
from bot.utils.seat_parser import parse_seats, SeatParseError


@dataclass
class RowResult:
    valid: bool
    row: Optional[int] = None  # None if invalid


@dataclass
class SeatResult:
    valid: bool
    seats: Optional[List[int]] = None  # None if invalid


async def handle_row_input(message: Message) -> RowResult:
    """
    Parse and validate a row number from message.text.
    Sends error reply if invalid. Returns RowResult.

    The caller is responsible for state transitions.
    """
    text = message.text.strip()
    try:
        row = int(text)
    except ValueError:
        min_row, max_row = get_row_range()
        await message.answer(f"Неверный формат. Введите номер ряда ({min_row}-{max_row}):")
        return RowResult(valid=False)

    if not is_valid_row(row):
        min_row, max_row = get_row_range()
        await message.answer(
            f"Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"
        )
        return RowResult(valid=False)

    return RowResult(valid=True, row=row)


async def handle_seat_input(message: Message, row: int) -> SeatResult:
    """
    Parse and validate seat numbers from message.text for the given row.
    Sends error reply if invalid. Returns SeatResult.

    The caller checks availability and decides state transitions.
    """
    text = message.text.strip()
    try:
        seats = parse_seats(text)
    except SeatParseError as e:
        await message.answer(f"Ошибка ввода: {e}\n\nПопробуйте снова:")
        return SeatResult(valid=False)

    from bot.utils.layout import is_valid_seat, get_seat_count
    seat_count = get_seat_count(row)
    invalid = [s for s in seats if not is_valid_seat(row, s)]

    if invalid:
        await message.answer(
            f"Недопустимые номера мест: {', '.join(map(str, invalid))}.\n"
            f"Для ряда {row} доступны места 1-{seat_count}.\n\n"
            f"Введите другие места:"
        )
        return SeatResult(valid=False)

    return SeatResult(valid=True, seats=seats)


async def handle_confirmation(message: Message) -> Optional[bool]:
    """
    Parse a Подтвердить/Отмена button press.
    Returns True (confirmed), False (cancelled), or None (unknown input).
    Sends re-prompt on None.
    """
    from bot.constants import Btn
    from bot.keyboards import confirmation_keyboard
    text = message.text.strip()
    if text == Btn.CONFIRM:
        return True
    if text == Btn.CANCEL:
        return False
    await message.answer("Выберите действие:", keyboard=confirmation_keyboard())
    return None
```

**How handlers use steps:**

```python
# In reservation.py (after refactor)
@router.on_state(BotState.AWAITING_ROW)
async def awaiting_row_handler(message: Message, storage: RedisStorage):
    result = await handle_row_input(message)
    if not result.valid:
        return  # step already sent error reply

    context = await storage.get_context(message.from_id)
    context['current_row'] = result.row
    seat_count = get_seat_count(result.row)
    await message.answer(seats_prompt(result.row, seat_count))
    await storage.set(message.from_id, BotState.AWAITING_SEATS, **context)
```

The handler contains only flow-specific logic: which context key to update, which state to
transition to, what message to send on success.

---

## Component Dependency Graph

```
                    ┌─────────────┐
                    │  constants  │  (no deps)
                    └──────┬──────┘
                           │ imported by
           ┌───────────────┼──────────────────┐
           │               │                  │
    ┌──────▼──────┐  ┌─────▼─────┐   ┌───────▼──────┐
    │  keyboards  │  │   texts   │   │   messages   │
    └──────┬──────┘  └─────┬─────┘   └──────┬───────┘
           │               │                 │
           └───────┬───────┘                 │
                   │                         │
            ┌──────▼──────┐                  │
            │    steps    │                  │
            └──────┬──────┘                  │
                   │                         │
            ┌──────▼──────┐                  │
            │   router    │◄─────────────────┘
            └──────┬──────┘
                   │ handlers registered on
            ┌──────▼──────┐
            │  handlers/  │ (7 files)
            └──────┬──────┘
                   │ loaded into
            ┌──────▼──────┐
            │   main.py   │
            └─────────────┘

Supporting (unchanged):
  fsm/states.py ← imported by router, handlers, steps
  fsm/storage.py ← imported by router, handlers, steps
  utils/db.py ← imported by handlers only
  utils/layout.py ← imported by steps, keyboards
  utils/seat_parser.py ← imported by steps
```

**Import rules to enforce:**
- `constants.py` imports nothing from `bot/`
- `texts.py` may import `bot.config` and `bot.utils.layout` (for row range)
- `steps.py` imports `constants`, `texts`, `keyboards`, `fsm/*`, `utils/layout`, `utils/seat_parser`
- `router.py` imports `vkbottle`, `fsm/*`, `constants`
- `handlers/*` import `router`, `steps`, `keyboards`, `messages`, `texts`, `constants`, `utils/db`
- `main.py` imports `router` and all handler modules
- **No handler imports another handler** (except the existing `show_main_menu` pattern — see below)

---

## The `show_main_menu` Cross-Import Problem

Currently `reservation.py`, `deletion.py`, `payment.py`, and `menu.py` all import
`from bot.handlers.menu import show_main_menu`. This is a cross-handler dependency that
creates import ordering fragility.

**Solution:** Move `show_main_menu` to `menu.py` (it already lives there) but expose it as
a shared utility by making it importable from a non-handler module.

Option A: Move `show_main_menu` into `bot/steps.py` as a step. Clean, but steps.py grows.

Option B: Create `bot/flows.py` for shared multi-step transitions that don't fit in steps.
`show_main_menu` would live there as `transition_to_main_menu(...)`.

Option C: Keep it in `menu.py` and accept the cross-handler import. The current code
already does this without issues — the circular import risk is low because `menu.py` doesn't
import from `reservation.py`, `deletion.py`, or `payment.py` (they import from it, not
the other way around).

**Recommendation:** Option C for now. The import is one-directional and well-established.
Refactor to Option B only if `menu.py` starts importing from other handlers.

---

## State Back-Navigation Design

**Current approach:** Back-navigation is handled ad-hoc. Confirmation handlers
(`DELETION_CONFIRM`, `CANCEL_CONFIRM`, `RESERVE_REMOVE_CONFIRM`) call `show_main_menu()`
on both confirm and cancel. There is no generic "go back" mechanism.

**Proposed: Parent State Map**

A dict mapping each state to its logical parent state. Used by a generic `go_back()`
helper and by `handle_confirmation()` when the user cancels.

```python
# bot/fsm/states.py (addition)

PARENT_STATE: dict[BotState, BotState | None] = {
    # Reservation creation flow
    BotState.IDLE:                  None,               # no parent
    BotState.AWAITING_ROW:          BotState.MAIN_MENU, # cancel -> main menu
    BotState.AWAITING_SEATS:        BotState.AWAITING_ROW,
    BotState.SEAT_ADDITION_MENU:    BotState.AWAITING_SEATS,

    # Main menu and deletion flow
    BotState.MAIN_MENU:             BotState.IDLE,      # cancel -> idle
    BotState.DELETING_ROW:          BotState.MAIN_MENU,
    BotState.DELETING_SEATS:        BotState.DELETING_ROW,
    BotState.DELETION_CONFIRM:      BotState.DELETING_SEATS,
    BotState.CANCEL_CONFIRM:        BotState.MAIN_MENU,
    BotState.CONTEXT_SWITCH_CONFIRM: None,              # handled specially: restore original_state

    # Payment flow
    BotState.PAYMENT_QUANTITY:      BotState.MAIN_MENU,

    # Reserve flow (admin only)
    BotState.RESERVE_ACTION:        BotState.IDLE,
    BotState.RESERVE_ADDING_ROW:    BotState.RESERVE_ACTION,
    BotState.RESERVE_ADDING_SEATS:  BotState.RESERVE_ADDING_ROW,
    BotState.RESERVE_COMMENT:       BotState.RESERVE_ADDING_SEATS,
    BotState.RESERVE_REMOVING_ROW:  BotState.RESERVE_ACTION,
    BotState.RESERVE_REMOVING_SEATS: BotState.RESERVE_REMOVING_ROW,
    BotState.RESERVE_REMOVE_CONFIRM: BotState.RESERVE_REMOVING_SEATS,
}
```

**Important nuance — context dependency:**

Back-navigation cannot always be a simple `storage.set(peer_id, parent_state)` because
some states depend on context from the forward journey. For example, going back from
`AWAITING_SEATS` to `AWAITING_ROW` works fine (context already has reservation_id). But
going back from `SEAT_ADDITION_MENU` to main menu requires `show_main_menu()` which needs
`reservation_id`, `buyer_vk_user_id`, `buyer_vk_api_id`, and `buyer_display_name` from context.

The parent map is useful as documentation and for a generic `/cancel` handler, but deep
back-navigation within a flow still needs flow-specific logic.

**Generic `/cancel` using the parent map:**

```python
# In commands.py (after refactor)
@router.on_command(Cmd.CANCEL_RU, "/cancel")
async def cancel_handler(message: Message, storage: RedisStorage):
    state_peer = await storage.get(message.from_id)
    if state_peer is None:
        await message.answer("Нет активной операции.", keyboard=commands_keyboard())
        return

    current_state = state_peer.state  # string like "BotState:main_menu"
    # Map string back to BotState for lookup
    # (or store BotState directly — depends on how get_state_repr works)
    await storage.delete(message.from_id)
    await message.answer(
        "Операция отменена. Состояние сброшено.\n\nЧтобы начать заново, перешлите сообщение клиента.",
        keyboard=commands_keyboard(),
    )
```

Cancel clears state unconditionally — it goes to IDLE, not to parent. The parent map is
more useful for "back" buttons within flows (not yet implemented, but designed for).

---

## Migration Order

Build order is determined by dependency graph: start with leaves (no deps), end at root.

### Step 1: `bot/constants.py` — Independent, pure value

Creates `Btn` and `Cmd` StrEnum classes.
**Testable immediately:** `assert Btn.CONFIRM == "Подтвердить"`.
**No changes to handlers yet.** This file can sit unused until Step 3.

### Step 2: `bot/texts.py` — Independent, pure value

Extracts inline prompt strings from handlers.
**Testable immediately:** `assert "Введите номер ряда" in texts.row_prompt()`.
**No changes to handlers yet.**

### Step 3: `bot/keyboards.py` update — Use constants

Replace raw string literals in `keyboards.py` with `Btn.*` values.
Example: `Text("Добавить еще")` → `Text(Btn.ADD_MORE)`.
**This is a zero-behavior-change refactor.** StrEnum equality holds.
Run existing tests after this step.

### Step 4: `bot/steps.py` — Depends on constants, texts, layout, seat_parser

Implement `handle_row_input`, `handle_seat_input`, `handle_confirmation`.
**Testable in isolation:** unit tests can call steps with mock messages.
**No handler changes yet.** Steps are additive.

### Step 5: `bot/router.py` — Depends on vkbottle BotLabeler, fsm/*

Implement `Router` class with `on_state`, `on_command`, `on_message` decorators.
**Testable:** instantiate Router with a mock storage, verify labeler has correct handlers.
**No handler changes yet.** Router is additive.

### Step 6: Refactor one handler file to use router + steps

Start with the simplest: `bot/handlers/reservation.py`.
Migrate `awaiting_row_handler` and `awaiting_seats_handler` to use `steps.handle_row_input`
and `steps.handle_seat_input`. Replace raw string literals with `texts.*` and `Btn.*`.
Replace `register_handlers(bot)` with `@router.on_state(BotState.X)` decorators.
**Testable:** bot still runs with mixed old/new style during migration.

### Step 7: Refactor remaining handler files

Order: deletion, reserve (both have the most duplication), then menu, payment, commands,
debtors.

For `menu.py` and `reserve.py`: remove the `elif text.startswith("/"):` re-dispatch blocks.
These become dead code once command handlers are registered before state handlers.

### Step 8: Update `bot/main.py`

Replace `register_handlers(bot)` calls with `bot.labeler.load(router.labeler)`.
Ensure command handlers load first (they're added to router first in router.py, and
router.labeler.handlers is a list, so order is preserved through `.load()`).

### Step 9: Migrate messages to `bot/texts.py`

Move remaining inline strings (complex multi-line prompts) from handlers into `texts.py`.
This is purely cosmetic — behavior does not change.

### Step 10: Add `PARENT_STATE` map to `bot/fsm/states.py`

No behavior change — map is only used by helpers that don't exist yet.
Document the state topology as data rather than comments.

---

## Concreteness Check: How `router.py` Connects to vkbottle

```python
# bot/main.py (after refactor)
from bot.router import Router
from bot.handlers import commands, reservation, menu, deletion, payment, reserve, debtors

async def setup():
    redis_storage = RedisStorage(...)
    await redis_storage.connect()

    # Create shared router with storage injected once
    router = Router(storage=redis_storage)

    # Register handlers on router (each handler module uses @router.on_state etc.)
    # Handler modules are imported; decorators run at import time
    # (decorators call router.labeler.message(...) internally)

    # Initialize bot
    bot = Bot(token=config.VK_BOT_TOKEN, state_dispenser=redis_storage)

    # Load all handlers into bot's labeler
    # NOTE: command handlers must be loaded before state handlers
    bot.labeler.load(router.labeler)

    return bot
```

**Handler module pattern (after refactor):**
```python
# bot/handlers/reservation.py
from bot.router import router  # module-level singleton, or passed in
from bot.fsm.states import BotState
from bot.steps import handle_row_input, handle_seat_input

@router.on_state(BotState.AWAITING_ROW)
async def awaiting_row_handler(message, storage):
    result = await handle_row_input(message)
    if not result.valid:
        return
    # ... flow-specific logic
```

**Module-level router singleton vs. passed-in router:**

Option A (singleton): `bot/router.py` exports a module-level `router = Router(storage=None)`,
storage is injected later via `router.storage = redis_storage`. Cleaner imports but global state.

Option B (passed-in): `Router` is instantiated in `main.py` and passed to each handler
module's `register(router)` function. More explicit, no global state.

**Recommendation:** Option B. The existing code already uses the `register_handlers(bot)`
pattern. Changing the signature from `register_handlers(bot)` to `register(router)` is
a minimal mechanical change that avoids global state.

---

## Architecture Patterns to Follow

### Pattern: Thin Decorator, Fat Handler Body

The router decorator only injects storage. Business logic stays in the handler. Avoid
adding logic to the decorator layer (no auto-state-management, no auto-keyboard-restoration).

### Pattern: Steps Return Results, Handlers Decide

Steps validate input and send error replies. They return a result object. The handler
decides what state transition to make on success. Steps have no knowledge of BotState.

### Pattern: Context is the Source of Truth

All flow state is in `storage.get_context(peer_id)`. Never derive context from the
current state — always read it from storage explicitly. This makes handlers order-independent
and testable.

### Pattern: One State = One Handler Function

Every `BotState` value has exactly one handler function registered for it. Cross-state
logic goes into shared steps or utility functions, not into handlers.

---

## Anti-Patterns to Avoid

### Anti-Pattern: State-Aware Steps

Steps should not call `storage.set(...)`. Steps validate and parse. Handlers transition.
If a step changes state, you can't reuse it across flows with different target states.

### Anti-Pattern: Middleware for Command Dispatch

Implementing command interception as middleware that reads `message.text` and does full
dispatch is over-engineering. Registration order in the handler list is sufficient and
simpler. Only use middleware for cross-cutting concerns that are genuinely orthogonal to
routing (e.g., logging, rate limiting).

### Anti-Pattern: StrEnum Values in Message Text Templates

Don't use `Btn.CONFIRM` inside message text strings like
`f"Нажмите {Btn.CONFIRM} для подтверждения"`. If the button label changes, both the
constant and the message text change anyway. Constants are for matching incoming text and
building keyboard labels — not for embedding in prose.

### Anti-Pattern: Context Rebuild on Back-Navigation

When navigating back to a previous state, do not re-run the forward logic to rebuild
context. The context already exists in storage from when the user first entered that state.
Just restore the state with the existing context.

---

## Scalability Considerations

| Concern | Current (1-10 users) | Post-refactor | At scale (not relevant for this bot) |
|---------|---------------------|---------------|--------------------------------------|
| Storage injection | Closure per handler | Once in Router constructor | — |
| Adding new command | Edit commands.py + menu.py + reserve.py | Edit commands.py only | — |
| Adding new state | Add to BotState + handler + PARENT_STATE | Same | — |
| Adding new flow | Copy-paste row/seat validation | Use steps.handle_row_input | — |
| Testing a handler | Requires full bot setup | Can unit-test with mock storage | — |

---

## Sources

- vkbottle 4.6.2 source: `.venv/lib/python3.14/site-packages/vkbottle/`
  - `framework/labeler/base.py` — `BaseLabeler.load()`, `BaseLabeler.message()`
  - `dispatch/views/abc/message.py` — handler evaluation order, blocking behavior
  - `dispatch/rules/base.py` — `StateRule.check()`, how state matching works
  - `dispatch/middlewares/abc.py` — `BaseMiddleware` interface
  - `framework/bot/bot.py` — `Bot.on` is `bot.labeler`, how router is constructed
- All 7 handler files read directly to catalog duplication and injection patterns
- `bot/fsm/storage.py` — `RedisStorage.set()`, context model
- `bot/fsm/states.py` — all 16 `BotState` values verified for PARENT_STATE map

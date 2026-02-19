# Technology Stack: VK Bot Architecture Refactoring

**Project:** Tickets VK Bot — Phase 2 refactoring
**Researched:** 2026-02-19
**Confidence:** HIGH — all findings sourced from installed vkbottle source (`.venv`) and live Python 3.14 runtime

---

## 1. StrEnum for Button/Command Constants

### Recommendation: stdlib `StrEnum` (Python 3.11+), no extensions needed

**Verified against Python 3.14.0 runtime.**

`StrEnum` (introduced in Python 3.11, `enum.StrEnum`) is a `str` subclass — instances pass `isinstance(x, str)` and compare equal to their string values. No third-party library is needed.

```python
from enum import StrEnum

class Cmd(StrEnum):
    START   = "/start"
    HELP    = "/Справка"
    CANCEL  = "/Отмена"
    DEBTORS = "/Должники"
    RESERVE = "/Резерв"

class Btn(StrEnum):
    ADD        = "Добавить"
    DELETE     = "Удалить"
    DELETE_ALL = "Удалить все"
    PAYMENT    = "Оплата"
    ADD_MORE   = "Добавить еще"
    DONE       = "Готово"
    CONFIRM    = "Подтвердить"
    CANCEL_INLINE = "Отмена"
    YES        = "Да"
    NO         = "Нет"
    REFRESH    = "Обновить"

ALL_COMMANDS: frozenset[str] = frozenset(Cmd)
```

**Verified behaviors (Python 3.14):**

| Operation | Result | Verified |
|-----------|--------|----------|
| `Btn.ADD == "Добавить"` | `True` | Yes |
| `"Добавить" in frozenset(Btn)` | `True` | Yes |
| `isinstance(Btn.ADD, str)` | `True` — passes vkbottle's `text=` param | Yes |
| `f"{Btn.ADD}"` | `"Добавить"` | Yes |
| `bot.on.message(text=Btn.CANCEL)` | works — `text=` accepts `str` | Yes (StrEnum is str) |

**No extensions needed.** `StrEnum` alone satisfies all usage:
- Handler conditions: `if text == Btn.ADD:` (direct string comparison)
- Keyboard builders: `Keyboard().add(Text(Btn.ADD))` (StrEnum is str)
- Command membership: `if text in ALL_COMMANDS:` (frozenset of StrEnum values)
- vkbottle `text=` parameter: accepts `str` or `List[str]` — StrEnum passes both

---

## 2. vkbottle Handler Registration — Built-in Patterns vs Custom Router

### What vkbottle actually provides (verified from installed source)

**vkbottle 4.x architecture:**

```
Bot
├── .on (BotLabeler) — decorator interface
│   ├── .message(*rules, **custom_rules) — registers to message_view.handlers list
│   ├── .private_message(...)
│   └── .raw_event(...)
├── labeler.message_view.handlers — List[FromFuncHandler], checked in order
└── labeler.message_view.middlewares — List[Type[BaseMiddleware]]
```

**Handler registration (the existing pattern):**

```python
# Current pattern
bot.on.message(text="/cancel")(handler_func)
bot.on.message(state=BotState.AWAITING_ROW)(handler_func)
```

These custom rule shortcuts map to built-in `ABCRule` subclasses:
- `text=` → `VBMLRule` (or `TextRule` via DEFAULT_CUSTOM_RULES["text"])
- `state=` → `StateRule`
- `state_group=` → `StateGroupRule`
- `func=` → `FuncRule` (callable predicate)
- `coro=` / `coroutine=` → `CoroutineRule` (async predicate)
- `regexp=` / `regex=` → `RegexRule`

**Handler dispatch logic (verified from `ABCMessageView.handle_event`):**
1. `pre_middleware()` runs all middleware `pre()` hooks — if any returns error, stop entirely
2. Iterate `self.handlers` in registration order
3. Each handler's rules are checked via `filter()`
4. First handler where all rules pass AND `blocking=True` wins, stops iteration
5. `post_middleware()` runs after

**The BotBlueprint is deprecated** (confirmed: `@deprecated(...)` in `blueprint.py`). Official migration is toward code separation via separate `BotLabeler` instances loaded together.

### Recommendation: Custom Router wrapping `bot.on.message()`

**Do NOT use `BotBlueprint`** — it is deprecated with a FutureWarning. The official separation approach is a standalone `BotLabeler` per module, loaded into the bot labeler. However, for this codebase's needs, a **thin custom Router class wrapping `bot.on.message()`** is simpler and eliminates closures without requiring the blueprint pattern.

```python
# bot/router.py
from vkbottle.bot import Bot, Message
from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.constants import Cmd, ALL_COMMANDS

HandlerFunc = Callable[[Message, RedisStorage], Awaitable[None]]
CommandHandlerFunc = Callable[[Message, RedisStorage], Awaitable[None]]

class Router:
    """
    Central handler registry. Eliminates closure boilerplate and centralizes
    command dispatch interception.

    How it works:
    - Collects decorators into internal dicts/lists during module load
    - register_all(bot) wires everything into vkbottle at startup
    - State handlers are wrapped with a command interceptor
    """

    def __init__(self, storage: RedisStorage):
        self._storage = storage
        self._state_handlers: dict[BotState, HandlerFunc] = {}
        self._command_handlers: dict[str, CommandHandlerFunc] = {}
        self._text_handlers: dict[str, HandlerFunc] = {}
        self._forwarded_handler: HandlerFunc | None = None

    def on_state(self, state: BotState):
        """Decorator: register handler for a specific FSM state."""
        def decorator(func: HandlerFunc) -> HandlerFunc:
            self._state_handlers[state] = func
            return func
        return decorator

    def on_command(self, *commands: Cmd):
        """Decorator: register handler for one or more commands."""
        def decorator(func: CommandHandlerFunc) -> CommandHandlerFunc:
            for cmd in commands:
                self._command_handlers[str(cmd)] = func
            return func
        return decorator

    def on_text(self, *texts: str):
        """Decorator: register stateless handler for exact text matches."""
        def decorator(func: HandlerFunc) -> HandlerFunc:
            for text in texts:
                self._text_handlers[str(text)] = func
            return func
        return decorator

    def on_forwarded(self):
        """Decorator: register handler for forwarded messages (no state)."""
        def decorator(func: HandlerFunc) -> HandlerFunc:
            self._forwarded_handler = func
            return func
        return decorator

    def _make_state_handler(self, handler: HandlerFunc):
        """Wrap state handler with command interceptor."""
        storage = self._storage

        async def wrapped(message: Message):
            text = message.text.strip()
            if text in ALL_COMMANDS and text in self._command_handlers:
                # Command typed mid-flow: clear state, dispatch to command handler
                await storage.delete(message.from_id)
                await self._command_handlers[text](message, storage)
                return
            await handler(message, storage)

        return wrapped

    def _make_command_handler(self, handler: CommandHandlerFunc):
        """Wrap command handler with storage injection."""
        storage = self._storage

        async def wrapped(message: Message):
            await handler(message, storage)

        return wrapped

    def _make_stateless_handler(self, handler: HandlerFunc):
        """Wrap stateless handler with storage injection."""
        storage = self._storage

        async def wrapped(message: Message):
            await handler(message, storage)

        return wrapped

    def register_all(self, bot: Bot) -> None:
        """Wire all collected handlers into vkbottle."""

        # 1. Command handlers (text match, any state, highest priority — registered first)
        for cmd_text, handler in self._command_handlers.items():
            bot.on.message(text=cmd_text)(self._make_command_handler(handler))

        # 2. Stateless text handlers (e.g., "Обновить" for debtors)
        for text, handler in self._text_handlers.items():
            bot.on.message(text=text)(self._make_stateless_handler(handler))

        # 3. State handlers (state match, wrapped with command interceptor)
        for state, handler in self._state_handlers.items():
            bot.on.message(state=state)(self._make_state_handler(handler))

        # 4. Forwarded message handler (no state, no text — catch-all for idle users)
        if self._forwarded_handler:
            storage = self._storage
            handler = self._forwarded_handler
            async def forwarded_wrapped(message: Message):
                await handler(message, storage)
            bot.on.message(state=BotState.IDLE)(forwarded_wrapped)
```

**Handler files with decorator usage:**

```python
# bot/handlers/commands.py
@router.on_command(Cmd.START)
async def start_handler(message: Message, storage: RedisStorage):
    await message.answer(texts.WELCOME, keyboard=keyboards.commands())

@router.on_command(Cmd.CANCEL, "/cancel")
async def cancel_handler(message: Message, storage: RedisStorage):
    await storage.delete(message.from_id)
    await message.answer(texts.CANCEL_DONE, keyboard=keyboards.commands())

# bot/handlers/reservation.py
@router.on_state(BotState.AWAITING_ROW)
async def awaiting_row(message: Message, storage: RedisStorage):
    await steps.handle_row_input(message, storage, next_state=BotState.AWAITING_SEATS)
```

**main.py after refactoring:**

```python
# Initialize router once, pass to handler modules
storage = RedisStorage(...)
router = Router(storage)

# Import modules — decorators fire at import time, registering into router
from bot.handlers import commands, reservation, menu, deletion, payment, reserve, debtors

# Wire everything into vkbottle
router.register_all(bot)
```

### Why not use vkbottle's BaseMiddleware for command interception?

`BaseMiddleware` runs before ALL handlers, including text-matched command handlers. If the middleware fires for `/cancel` text during an idle state (no FSM state), it would intercept the command handler that was already going to fire correctly. The wrapper-based approach is more surgical: it only applies command interception inside state-specific handlers.

Additionally, `BaseMiddleware.stop()` suppresses the entire view including any post-middleware. The wrapper pattern lets command dispatch happen cleanly without side effects.

**Using BaseMiddleware is correct for:** cross-cutting concerns (logging, rate limiting, auth checks). **Not recommended** for command-vs-state dispatch because it intercepts all messages unconditionally.

---

## 3. State Machine Back-Navigation Pattern

### Problem

The plan calls for `/cancel` going back one state (instead of resetting to IDLE). This requires storing the previous state in FSM context and restoring it on cancel.

### Critical vkbottle state storage detail

**`BaseStateGroup` stores as `"ClassName:value"` (e.g., `"BotState:awaiting_row"`)**, not just the enum value. This is implemented in `get_state_repr()` in `dispenser/base.py`.

When you call `storage.set(peer_id, BotState.AWAITING_ROW)`, vkbottle stores `"BotState:awaiting_row"` as the state string. The `StateRepresentation` class has a custom `__eq__` that handles comparison against `BaseStateGroup` instances, enabling `StateRule` to match correctly.

**The existing bug in `context_switch_handler`** (line 325 of menu.py): it stores `original_state` from payload as a raw string, then passes it back to `storage.set()`. Since plain `str` stored in a payload is serialized by JSON as a plain string (not a `StateRepresentation`), passing it back to `storage.set()` bypasses the `StateRepresentation` wrapping and the `StateRule` check fails.

**The fix (from REFACTORING_PLAN.md section 2.6):**
```python
# Buggy:
await storage.set(message.from_id, original_state, **original_context)

# Fixed: restore enum from .value string stored in payload
await storage.set(message.from_id, BotState(original_state), **original_context)
# This only works if original_state was stored as .value ('awaiting_row'), not full repr
```

### Recommended back-navigation pattern

**Store the previous state's `.value` (not the full repr) in the FSM payload.**

```python
# When transitioning forward, record where we came from:
async def handle_row_input(message, storage, next_state, prev_state, ...):
    context = await storage.get_context(message.from_id)
    context["previous_state"] = prev_state.value  # store 'awaiting_row', not 'BotState:awaiting_row'
    await storage.set(message.from_id, next_state, **context)

# When /cancel is pressed (back-navigation):
@router.on_command(Cmd.CANCEL)
async def cancel_handler(message: Message, storage: RedisStorage):
    context = await storage.get_context(message.from_id)
    prev_state_value = context.get("previous_state")  # e.g. 'awaiting_row'

    if prev_state_value:
        # Go back one step, clear the previous_state entry
        prev_state = BotState(prev_state_value)  # reconstructed enum
        context.pop("previous_state", None)
        await storage.set(message.from_id, prev_state, **context)
        await message.answer(texts.BACK_TO_PREVIOUS, keyboard=keyboards.commands())
    else:
        # No previous state — full reset to IDLE
        await storage.delete(message.from_id)
        await message.answer(texts.CANCEL_DONE, keyboard=keyboards.commands())
```

**Verified:** `BotState('awaiting_row')` correctly reconstructs `BotState.AWAITING_ROW` (Python 3.14 runtime test). The reconstructed enum passes through `StatePeer.validate_state()` and becomes a `StateRepresentation`, so `StateRule` matching works.

### /cancel vs /exit distinction

Per the project spec:
- `/cancel` (Cmd.CANCEL = `/Отмена`) — go back one state
- `/exit` (if added) — reset to IDLE

The back-navigation handler above implements this. The command interceptor in `_make_state_handler()` must dispatch to the appropriate handler:
```python
# In _make_state_handler wrapper:
if text in ALL_COMMANDS and text in self._command_handlers:
    # For /Отмена: calls cancel_handler which checks previous_state
    await self._command_handlers[text](message, storage)
    return
```

No state clearing is done by the interceptor — the cancel_handler itself decides whether to go back or reset.

---

## 4. Decorator-Based Handler Registration Patterns

### How registration works in practice

vkbottle's `bot.on.message(...)` is itself a decorator factory. The decorator it returns appends a `FromFuncHandler` to `labeler.message_view.handlers`. Registration happens at call time (not at class definition time).

**The pattern used in this codebase's router:**

1. Module-level decorators fire at import time — `@router.on_state(BotState.X)` stores the function in `router._state_handlers`
2. `router.register_all(bot)` is called once after all modules are imported — this converts stored functions into wrapped handlers and calls `bot.on.message(...)` for each

This is safe and idiomatic. The alternative (decorator fires immediately calling `bot.on.message`) requires `bot` to be available at import time, creating circular dependency issues.

**Handler function signatures:**

vkbottle's `FromFuncHandler.handle()` uses `magic_bundle` to inject only the parameters the function actually declares. However, the router wraps all handlers in plain closures (`wrapped(message: Message)`) that call the underlying handler with explicit `(message, storage)`. This is simpler and type-checker-friendly than magic injection.

```python
# Pattern: all handler functions take (message, storage)
async def my_handler(message: Message, storage: RedisStorage) -> None:
    ...

# Router wraps at registration time:
async def wrapped(message: Message):
    await my_handler(message, router._storage)
bot.on.message(state=BotState.X)(wrapped)
```

### Decorator ordering

Registration order = priority. The router registers in this order:
1. Command handlers (`text=Cmd.X`) — checked first, match regardless of state
2. Stateless text handlers (`text="Обновить"`) — also text-matched, checked next
3. State handlers (`state=BotState.X`) — only match when user is in that state

Since `blocking=True` is the default, the first matching handler wins and stops evaluation. This means:
- `/Отмена` text during any state always hits the command handler (registered first)
- State handlers only fire for non-command text

---

## 5. Complete Stack Summary

| Component | Technology | Version | Source |
|-----------|------------|---------|--------|
| Bot framework | vkbottle | installed in .venv | direct inspection |
| FSM state storage | Redis + custom RedisStorage | existing | existing codebase |
| String constants | `enum.StrEnum` | stdlib, Python 3.11+ | Python 3.14 runtime test |
| Back-navigation | Store `.value` in payload, reconstruct with `BotState(value)` | n/a | vkbottle dispenser source |
| Command interception | Closure wrapper in Router, not BaseMiddleware | n/a | architectural choice |
| Handler registration | Custom `Router` wrapping `bot.on.message()` | n/a | vkbottle source analysis |
| Code separation | Custom Router (not BotBlueprint — deprecated) | n/a | blueprint.py deprecation |

---

## 6. Anti-Patterns to Avoid

### Anti-Pattern 1: Using BotBlueprint for code separation

`BotBlueprint` carries a `@deprecated(category=FutureWarning)` decorator in the installed vkbottle version. **Do not use.** Use the custom Router approach or standalone `BotLabeler` instances instead.

### Anti-Pattern 2: Storing full state repr (`"BotState:awaiting_row"`) in payload for back-navigation

Storing the full `get_state_repr()` output and passing it back to `storage.set()` fails because `storage.set()` passes the value through `StatePeer.validate_state()`, which only wraps it in `StateRepresentation` if it receives a `BaseStateGroup` instance. A plain string passes through as-is, and `StateRule` comparison then fails because `StateRepresentation.__eq__` with a plain string is just string equality, but `StateRepresentation.__eq__` with a `BaseStateGroup` invokes `get_state_repr()` for comparison.

**Use `.value` for storage, `BotState(.value)` for reconstruction.**

### Anti-Pattern 3: BaseMiddleware for command interception

`BaseMiddleware.pre()` intercepts ALL messages before any handler runs. Using `stop()` prevents ALL handlers including correctly-matched command text handlers. The wrapper-in-router approach is surgical and cleaner.

### Anti-Pattern 4: StrEnum with `.value` comparisons in handler code

Since `StrEnum` instances ARE strings, you never need `.value`:
```python
# Wrong — unnecessary:
if text == Btn.ADD.value:

# Correct — direct comparison works:
if text == Btn.ADD:
```

---

## Sources

All findings are HIGH confidence, sourced from:

- `/Users/thecattest/things/projects/Tickets/.venv/lib/python3.14/site-packages/vkbottle/` — installed package source (direct file reading)
  - `dispatch/dispenser/base.py` — `BaseStateGroup`, `StatePeer`, `get_state_repr`
  - `dispatch/views/abc/message.py` — `handle_event`, handler dispatch loop
  - `dispatch/views/abc/view.py` — `BaseMiddleware`, `register_middleware`, pre/post lifecycle
  - `dispatch/rules/base.py` — `StateRule`, `TextRule`, `CommandRule` implementations
  - `dispatch/handlers/from_func_handler.py` — `FromFuncHandler`, `magic_bundle`
  - `framework/labeler/base.py` — `BaseLabeler.message()`, `auto_rules`, handler list
  - `framework/bot/blueprint.py` — `BotBlueprint` deprecation notice
  - `framework/bot/bot.py` — `Bot.__init__`, `bot.on` property
- Python 3.14.0 runtime: live `python3 -c` tests for StrEnum and state reconstruction behavior
- `/Users/thecattest/things/projects/Tickets/REFACTORING_PLAN.md` — project intent and planned patterns
- `/Users/thecattest/things/projects/Tickets/bot/handlers/*.py` — existing handler patterns
- `/Users/thecattest/things/projects/Tickets/bot/fsm/storage.py` — custom RedisStorage implementation

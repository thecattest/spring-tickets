# Phase 10: Router - Research

**Researched:** 2026-02-19
**Domain:** vkbottle 4.6.2 labeler/handler registration, FSM dispatch, closure injection
**Confidence:** HIGH

## Summary

Phase 10 creates `bot/router.py` with a `Router` class that reads `FSM_CONFIG` (from Phase 9's `bot/fsm/config.py`) and registers all handlers into a single `BotLabeler` in the correct order. `bot/main.py` then calls `bot.labeler.load(router.labeler)` once instead of seven `register_handlers()` calls.

The core mechanism is vkbottle's handler dispatch order: `BotMessageView.handle_event()` iterates `message_view.handlers` sequentially and stops at the first handler where `handler.blocking=True` and all rules pass. Since command handlers registered with a text rule (no `state=` rule) pass regardless of `state_peer`, registering them **before** state handlers achieves universal command interception (RTR-02) for free.

`labeler.load(other_labeler)` calls `self.message_view.handlers.extend(other_labeler.message_view.handlers)` — simple list extension, preserving registration order. The Router builds all handlers into its own `BotLabeler`, then the single `bot.labeler.load(router.labeler)` call transfers them in the correct order.

**Primary recommendation:** The Router class owns a `BotLabeler` instance and a storage reference. `register_all()` registers handlers in three groups: forwarded handler first, command handlers second, state handlers third. Each registration wraps the real handler in a closure that injects storage. Phase 10 does NOT migrate actual handler logic — it only wires the existing handler functions through this new registration infrastructure.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `vkbottle.framework.labeler.bot.BotLabeler` | 4.6.2 (installed) | Central handler registry; `load()` merges into bot | Already used by `bot.on` decorator; `bot.labeler.load()` is the documented multi-labeler pattern |
| `vkbottle.bot.Bot` | 4.6.2 | Access `bot.state_dispenser` and `bot.labeler` | Existing |
| `vkbottle.BaseStateGroup` | 4.6.2 | State enum type for `state=` rule in labeler | Existing; `BotState` inherits from it |
| `bot.fsm.config.FSM_CONFIG` | Phase 9 | Declarative state config the Router reads | Created in Phase 9 |
| `bot.fsm.states.BotState` | Phase 8 | State enum for `state=BotState.X` registration | Existing |
| `bot.fsm.storage.RedisStorage` | Phase 8 | Storage passed to handlers; obtained from `bot.state_dispenser` | Existing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` | stdlib | No new dataclasses needed in Phase 10 | Only if Router gets optional config |
| `logging` | stdlib | Router startup log for registered handler count | Always |
| `typing.Callable` | stdlib | Type annotation for handler references | If type-annotating `handler` mappings |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `BotLabeler` as router's labeler | Building `FromFuncHandler` manually | Manual construction is internal API; BotLabeler is stable public API |
| Closure injection per handler | Middleware that injects storage | Middleware runs for every message; closure only runs when handler matches |
| `register_all()` single method | One register method per handler type | Single `register_all()` enforces RTR-03 ordering; separate methods allow wrong order |

**Installation:**
```bash
# No new packages — vkbottle 4.6.2 already installed
```

## Architecture Patterns

### Recommended Project Structure
```
bot/
├── fsm/
│   ├── config.py      # Existing (Phase 9): FSM_CONFIG with StateConfig entries
│   └── states.py      # Existing (Phase 8): BotState enum
├── handlers/          # Existing: actual handler functions (unchanged in Phase 10)
│   ├── commands.py    # start_handler, help_handler, cancel_handler
│   ├── reservation.py # forwarded_message_handler, awaiting_row_handler, etc.
│   ├── menu.py        # main_menu_handler, context_switch_handler
│   ├── deletion.py    # deleting_row_handler, deletion_confirm_handler, etc.
│   ├── payment.py     # payment_quantity_handler
│   ├── reserve.py     # reserve_command_handler, reserve_action_handler, etc.
│   └── debtors.py     # debtors_command_handler, refresh_debtors_handler
├── router.py          # NEW (Phase 10): Router class + register_all()
└── main.py            # MODIFIED (Phase 10): replaces 7 register_handlers() with router
```

### Pattern 1: Router owns BotLabeler, register_all() enforces order

**What:** `Router` holds a `BotLabeler` instance and `storage` reference. `register_all()` adds handlers in three sequential passes: forwarded handler, command handlers, state handlers. Handler functions are imported directly (no circular import risk since handlers don't import router).

**When to use:** This is the only pattern — it is the Router.

```python
# bot/router.py
import logging
from vkbottle.framework.labeler.bot import BotLabeler
from vkbottle.bot import Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage

logger = logging.getLogger(__name__)


class Router:
    """
    Central handler router.

    Reads handler references directly (not from FSM_CONFIG — handler field is None there).
    register_all() enforces RTR-03 ordering: forwarded first, commands second, states third.
    """

    def __init__(self, storage: RedisStorage) -> None:
        self.labeler = BotLabeler()
        self.storage = storage

    def register_all(self) -> None:
        """Register all handlers in required order (RTR-03)."""
        # Pass 1: forwarded-message handler (must be first — catches fwd before state handlers)
        self._register_forwarded()
        # Pass 2: command handlers (must be before state handlers — RTR-02 universal interception)
        self._register_commands()
        # Pass 3: state handlers (registered last — only match when no command matched)
        self._register_states()
        logger.info(
            "register_all() complete: %d handlers registered",
            len(self.labeler.message_view.handlers),
        )

    def _make_state_handler(self, handler_func):
        """Create storage-injected closure for state handler."""
        storage = self.storage

        async def wrapped(message: Message):
            await handler_func(message, storage)

        wrapped.__name__ = handler_func.__name__ + "_wrapped"
        return wrapped

    def _register_forwarded(self) -> None:
        from bot.handlers.reservation import forwarded_message_handler

        wrapped = self._make_state_handler(forwarded_message_handler)
        self.labeler.message(func=lambda msg: bool(msg.fwd_messages))(wrapped)
        logger.debug("Registered forwarded handler")

    def _register_commands(self) -> None:
        from bot.handlers.commands import start_handler, help_handler, cancel_handler
        from bot.handlers.reserve import reserve_command_handler
        from bot.handlers.debtors import debtors_command_handler, refresh_debtors_handler
        storage = self.storage

        # /start (no storage needed)
        self.labeler.message(text="/start")(start_handler)

        # /help (no storage needed)
        self.labeler.message(text=["/help", "/Справка"])(help_handler)

        # /cancel (needs storage)
        self.labeler.message(text=["/cancel", "/Отмена"])(
            self._make_state_handler(cancel_handler)
        )

        # /Резерв (needs storage, admin check inside handler)
        self.labeler.message(text=["/reserve", "/Резерв"])(
            self._make_state_handler(reserve_command_handler)
        )

        # /Должники (no storage needed — stateless)
        self.labeler.message(text=["/debtors", "/Должники"])(debtors_command_handler)

        # "Обновить" button (stateless debtors refresh)
        self.labeler.message(text="Обновить")(refresh_debtors_handler)

        logger.debug("Registered command handlers")

    def _register_states(self) -> None:
        from bot.handlers.reservation import (
            awaiting_row_handler,
            awaiting_seats_handler,
            seat_addition_menu_handler,
        )
        from bot.handlers.menu import main_menu_handler, context_switch_handler
        from bot.handlers.deletion import (
            deleting_row_handler,
            deleting_seats_handler,
            deletion_confirm_handler,
            cancel_confirm_handler,
        )
        from bot.handlers.payment import payment_quantity_handler
        from bot.handlers.reserve import (
            reserve_action_handler,
            reserve_adding_row_handler,
            reserve_adding_seats_handler,
            reserve_comment_handler,
            reserve_removing_row_handler,
            reserve_removing_seats_handler,
            reserve_remove_confirm_handler,
        )

        state_mappings = [
            (BotState.AWAITING_ROW, awaiting_row_handler),
            (BotState.AWAITING_SEATS, awaiting_seats_handler),
            (BotState.SEAT_ADDITION_MENU, seat_addition_menu_handler),
            (BotState.MAIN_MENU, main_menu_handler),
            (BotState.CONTEXT_SWITCH_CONFIRM, context_switch_handler),
            (BotState.DELETING_ROW, deleting_row_handler),
            (BotState.DELETING_SEATS, deleting_seats_handler),
            (BotState.DELETION_CONFIRM, deletion_confirm_handler),
            (BotState.CANCEL_CONFIRM, cancel_confirm_handler),
            (BotState.PAYMENT_QUANTITY, payment_quantity_handler),
            (BotState.RESERVE_ACTION, reserve_action_handler),
            (BotState.RESERVE_ADDING_ROW, reserve_adding_row_handler),
            (BotState.RESERVE_ADDING_SEATS, reserve_adding_seats_handler),
            (BotState.RESERVE_COMMENT, reserve_comment_handler),
            (BotState.RESERVE_REMOVING_ROW, reserve_removing_row_handler),
            (BotState.RESERVE_REMOVING_SEATS, reserve_removing_seats_handler),
            (BotState.RESERVE_REMOVE_CONFIRM, reserve_remove_confirm_handler),
        ]

        for state, handler_func in state_mappings:
            wrapped = self._make_state_handler(handler_func)
            self.labeler.message(state=state)(wrapped)

        logger.debug("Registered %d state handlers", len(state_mappings))
```

### Pattern 2: bot/main.py wires the Router

**What:** `setup()` creates `Router(storage)`, calls `register_all()`, then `bot.labeler.load(router.labeler)`.

```python
# bot/main.py (modified section in setup())

from bot.router import Router

# ... existing RedisStorage initialization ...

bot = Bot(token=config.VK_BOT_TOKEN, state_dispenser=redis_storage)

# Phase 10: Replace 7 register_handlers() calls with single Router
router = Router(redis_storage)
router.register_all()
bot.labeler.load(router.labeler)
logger.info("Router loaded: %d handlers registered", len(bot.labeler.message_view.handlers))

# Remove these 7 lines:
# commands.register_handlers(bot)
# reservation.register_handlers(bot)
# menu.register_handlers(bot)
# deletion.register_handlers(bot)
# payment.register_handlers(bot)
# reserve.register_handlers(bot)
# debtors.register_handlers(bot)
```

### Pattern 3: Auth guard approach

**What:** Auth guards in `FSM_CONFIG` have values `"any"`, `"seller"`, `"admin"`. Phase 10 does NOT enforce auth at the Router level via a separate rule. Auth is enforced inside each handler function already:
- `"seller"` states: `db.get_seller_id(message.from_id)` (auto-creates if missing)
- `"admin"` states: `db.is_user_admin(message.from_id)` check inside handler
- `"any"` states: no auth check needed

The `auth_guard` field in `StateConfig` is informational for Phase 10. The Router reads it only for logging or documentation — it does NOT add an auth rule to the labeler registration. This matches the decision: "Phase 10 only creates the Router infrastructure."

**Rationale:** Adding auth at labeler level (via `func=lambda m: db.is_user_admin(m.from_id)`) would make auth a synchronous DB call on every message before dispatch, and would silently drop messages rather than responding with an error. Current in-handler auth is preferable.

### Pattern 4: FSM_CONFIG relationship to Router

**What:** Phase 9 created `FSM_CONFIG` with `handler=None` on all entries. Phase 10 does NOT populate `FSM_CONFIG.handler` fields. Instead, the Router imports handler functions directly and maintains its own explicit mapping (`state_mappings` list). This is cleaner than mutating the config dict.

**Why not populate FSM_CONFIG.handler:** The `handler=None` decision was made in Phase 9 to avoid circular imports at config load time. Keeping handler references out of the config dict is the right call — the Router is the appropriate place for handler references.

**What the Router DOES use from FSM_CONFIG:** Nothing in Phase 10, actually. The Router's `_register_states()` maintains its own explicit state-to-handler mapping. `FSM_CONFIG` is read by Phase 12 (for `back_state` navigation). The Router could loop over `FSM_CONFIG` to validate coverage (ensure every state in config has a handler registered), but this is optional for Phase 10.

### Anti-Patterns to Avoid

- **Registering in wrong order:** State handlers before command handlers means commands don't intercept in active FSM states. `register_all()` must call `_register_forwarded()`, then `_register_commands()`, then `_register_states()` — in that exact order.
- **Adding auth rules to labeler:** `labeler.message(func=lambda m: db.is_user_admin(m.from_id), state=BotState.RESERVE_ACTION)` makes every message hit the DB before dispatch. Keep auth inside handlers.
- **Importing handlers at Router class definition time (module level):** All handler imports in `_register_commands()` and `_register_states()` must be inside those methods (lazy imports), not at the top of `router.py`. This prevents circular import risk and matches the Phase 9 established pattern.
- **Using `bot.on.message()` in router.py:** The Router uses `self.labeler.message()` (its own labeler), not `bot.on.message()`. The bot instance is never passed to the Router.
- **Forgetting to keep existing `register_handlers()` functions intact:** Phase 10 does NOT delete the existing `register_handlers()` functions from handler files. Those are removed in Phase 11. Phase 10 only adds router.py and modifies main.py.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Handler ordering enforcement | Conditional checks at dispatch time | Registration order in `BotLabeler.handlers` list | vkbottle already stops at first matching blocking handler |
| Storage injection | Passing `bot` instance to handlers | Closure wrapping with captured `storage` reference | Matches existing `_with_storage` pattern; simpler |
| State-from-any-state commands | Middleware that checks text before state dispatch | Register command handlers (text rule, no state) BEFORE state handlers | vkbottle dispatch order handles this natively |
| Router-level auth | Labeler `func=` rule calling DB for every message | Keep auth inside handler functions | In-handler auth gives proper user feedback; router-level auth silently drops messages |

**Key insight:** vkbottle's handler list is just a Python list. Ordering is registration order. The Router's only job is to call registrations in the right sequence. No framework magic needed.

## Common Pitfalls

### Pitfall 1: Handler imports at module level in router.py
**What goes wrong:** `from bot.handlers.reservation import forwarded_message_handler` at the top of `router.py` triggers full import of `reservation.py`, which imports `menu.py`, which imports `payment.py`. This chain may cause circular imports or import order issues at startup.
**Why it happens:** Natural Python habit.
**How to avoid:** All handler imports inside `_register_forwarded()`, `_register_commands()`, `_register_states()` methods. These methods are called from `register_all()`, which runs after all modules are initialized.
**Warning signs:** `ImportError` or `AttributeError` during `router.py` import.

### Pitfall 2: Wrong storage reference
**What goes wrong:** `Router(storage)` called before `redis_storage.connect()` completes, or `bot.state_dispenser` used after `Bot()` construction but before `RedisStorage` is assigned as `state_dispenser`.
**Why it happens:** Order of operations in `setup()`.
**How to avoid:** Create `Router(redis_storage)` AFTER `await redis_storage.connect()` and AFTER `Bot(token=..., state_dispenser=redis_storage)` — same order as current `register_handlers()` calls. The storage passed to Router must be the same instance passed to `Bot()`.
**Warning signs:** `RuntimeError: Redis not connected` in handler execution.

### Pitfall 3: Forgetting "Обновить" button handler
**What goes wrong:** `refresh_debtors_handler` (text="Обновить" button) is not a command but needs to be registered before state handlers, because in any FSM state, pressing "Обновить" should refresh debtors. However it is stateless (no storage needed).
**Why it happens:** It's not a `/command`, so it's easy to miss in command registration pass.
**How to avoid:** Register "Обновить" in `_register_commands()` pass (before state handlers). It uses text rule only, so it will match from any state.
**Warning signs:** "Обновить" button does nothing when user is in AWAITING_ROW or other active states.

### Pitfall 4: Manual command dispatch in menu.py and reserve.py still present
**What goes wrong:** After Phase 10, the Router registers `/cancel` before `MAIN_MENU` state handler. But `main_menu_handler` still has `if text.startswith("/"):` manual dispatch inside it. The manual dispatch becomes dead code — commands are intercepted before `main_menu_handler` runs. This is harmless in Phase 10 but misleading. Phase 11 removes it.
**Why it happens:** Phase 10 intentionally does NOT modify handler bodies (that's Phase 11).
**How to avoid:** Accept the dead code for now. Document it. Phase 11 removes it as part of handler migration.
**Warning signs:** None in Phase 10 — double-dispatch via manual fallback never fires because Router's command handlers are registered first.

### Pitfall 5: FSM_CONFIG has 18 states but only 17 need state registration
**What goes wrong:** `BotState.IDLE` is in `FSM_CONFIG` but is NOT registered as a state handler. IDLE is the forwarded-message handler (registered by `_register_forwarded()` with `func=` rule). Trying to register `state=BotState.IDLE` would register a handler that only matches when `state_peer.state == "idle"`, but the forwarded handler needs `state_peer is None` (no state set) OR state=IDLE. The forwarded handler's `func=lambda msg: bool(msg.fwd_messages)` is the correct rule.
**Why it happens:** Iterating FSM_CONFIG naively for all states.
**How to avoid:** `_register_states()` explicitly lists 17 states (all except IDLE). The forwarded handler is in its own `_register_forwarded()` pass.
**Warning signs:** Two handlers matching in IDLE: both the forwarded handler AND a spurious IDLE state handler.

### Pitfall 6: bot.labeler already has handlers from previous register_handlers() calls
**What goes wrong:** If any `register_handlers(bot)` call is left in `main.py` alongside `bot.labeler.load(router.labeler)`, handlers are registered twice. The first-registered handler wins (blocking=True), so duplicates are harmless but add noise.
**Why it happens:** Partial migration — some `register_handlers()` calls removed, some left.
**How to avoid:** Remove ALL 7 `register_handlers()` calls from `main.py` when adding the Router. Do it atomically in one commit.
**Warning signs:** `len(bot.labeler.message_view.handlers)` is roughly double expected count.

## Code Examples

Verified patterns from direct inspection of vkbottle 4.6.2 source:

### labeler.load() source (confirmed by inspection)
```python
# From vkbottle/framework/labeler/base.py (BotLabeler.load)
def load(self, labeler: "BaseLabeler"):
    self.message_view.handlers.extend(labeler.message_view.handlers)
    self.message_view.middlewares.extend(labeler.message_view.middlewares)
    self.raw_event_view.middlewares.extend(labeler.raw_event_view.middlewares)
    for event, handler_basements in labeler.raw_event_view.handlers.items():
        event_handlers = self.raw_event_view.handlers.setdefault(event, [])
        event_handlers.extend(handler_basements)
```

### handle_event dispatch (confirmed by inspection)
```python
# From vkbottle/dispatch/views/bot/message.py — BotMessageView.handle_event
for handler in self.handlers:  # iterates in registration order
    result = await handler.filter(message, context_variables)
    if result is False:
        continue
    # ... run handler ...
    if handler.blocking:
        break  # stops at first match (default: blocking=True)
```

### StateRule.check (confirmed by inspection)
```python
# StateRule only checks state_peer.state — not text, not attachments
async def check(self, event: BaseMessageMin) -> bool:
    if event.state_peer is None:
        return not self.state  # True when state list is empty (None state)
    return event.state_peer.state in self.state
```

### VBMLRule.check (confirmed by inspection)
```python
# VBMLRule (text= rule) only checks event.text — not state_peer
async def check(self, event: BaseMessageMin) -> Union[Optional[dict], bool]:
    for pattern in self.patterns:
        result = self.patcher.check(pattern, event.text)
        if result not in (None, False):
            return result
    return False
```

**Key insight confirmed:** A handler with only a VBMLRule (text= rule) matches ANY message with matching text, regardless of FSM state. Registering command handlers before state handlers is sufficient for universal interception.

### Complete bot/router.py (reference implementation)
```python
"""
bot/router.py — Central handler router.

Reads handler functions directly and registers them into a BotLabeler in
RTR-03 required order:
  1. Forwarded-message handler (first)
  2. Command handlers (text rule — intercept from any FSM state)
  3. State handlers (last — only match when no command matched)

Usage in bot/main.py:
    router = Router(redis_storage)
    router.register_all()
    bot.labeler.load(router.labeler)
"""

import logging
from vkbottle.framework.labeler.bot import BotLabeler
from vkbottle.bot import Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage

logger = logging.getLogger(__name__)


class Router:
    def __init__(self, storage: RedisStorage) -> None:
        self.labeler = BotLabeler()
        self.storage = storage

    def register_all(self) -> None:
        """Register all handlers in RTR-03 required order."""
        self._register_forwarded()
        self._register_commands()
        self._register_states()
        count = len(self.labeler.message_view.handlers)
        logger.info("Router: registered %d handlers", count)

    # --- Internal helpers ---

    def _wrap(self, handler_func):
        """Wrap handler with storage injection."""
        storage = self.storage
        async def wrapped(message: Message):
            await handler_func(message, storage)
        wrapped.__name__ = handler_func.__name__ + "_wrapped"
        return wrapped

    def _register_forwarded(self) -> None:
        from bot.handlers.reservation import forwarded_message_handler
        self.labeler.message(func=lambda msg: bool(msg.fwd_messages))(
            self._wrap(forwarded_message_handler)
        )

    def _register_commands(self) -> None:
        from bot.handlers.commands import start_handler, help_handler, cancel_handler
        from bot.handlers.reserve import reserve_command_handler
        from bot.handlers.debtors import debtors_command_handler, refresh_debtors_handler

        self.labeler.message(text="/start")(start_handler)
        self.labeler.message(text=["/help", "/Справка"])(help_handler)
        self.labeler.message(text=["/cancel", "/Отмена"])(self._wrap(cancel_handler))
        self.labeler.message(text=["/reserve", "/Резерв"])(self._wrap(reserve_command_handler))
        self.labeler.message(text=["/debtors", "/Должники"])(debtors_command_handler)
        self.labeler.message(text="Обновить")(refresh_debtors_handler)

    def _register_states(self) -> None:
        from bot.handlers.reservation import (
            awaiting_row_handler, awaiting_seats_handler, seat_addition_menu_handler,
        )
        from bot.handlers.menu import main_menu_handler, context_switch_handler
        from bot.handlers.deletion import (
            deleting_row_handler, deleting_seats_handler,
            deletion_confirm_handler, cancel_confirm_handler,
        )
        from bot.handlers.payment import payment_quantity_handler
        from bot.handlers.reserve import (
            reserve_action_handler, reserve_adding_row_handler,
            reserve_adding_seats_handler, reserve_comment_handler,
            reserve_removing_row_handler, reserve_removing_seats_handler,
            reserve_remove_confirm_handler,
        )

        states = [
            (BotState.AWAITING_ROW,            awaiting_row_handler),
            (BotState.AWAITING_SEATS,           awaiting_seats_handler),
            (BotState.SEAT_ADDITION_MENU,       seat_addition_menu_handler),
            (BotState.MAIN_MENU,                main_menu_handler),
            (BotState.CONTEXT_SWITCH_CONFIRM,   context_switch_handler),
            (BotState.DELETING_ROW,             deleting_row_handler),
            (BotState.DELETING_SEATS,           deleting_seats_handler),
            (BotState.DELETION_CONFIRM,         deletion_confirm_handler),
            (BotState.CANCEL_CONFIRM,           cancel_confirm_handler),
            (BotState.PAYMENT_QUANTITY,         payment_quantity_handler),
            (BotState.RESERVE_ACTION,           reserve_action_handler),
            (BotState.RESERVE_ADDING_ROW,       reserve_adding_row_handler),
            (BotState.RESERVE_ADDING_SEATS,     reserve_adding_seats_handler),
            (BotState.RESERVE_COMMENT,          reserve_comment_handler),
            (BotState.RESERVE_REMOVING_ROW,     reserve_removing_row_handler),
            (BotState.RESERVE_REMOVING_SEATS,   reserve_removing_seats_handler),
            (BotState.RESERVE_REMOVE_CONFIRM,   reserve_remove_confirm_handler),
        ]

        for state, handler_func in states:
            self.labeler.message(state=state)(self._wrap(handler_func))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 7 `register_handlers(bot)` calls in main.py | `router.register_all(); bot.labeler.load(router.labeler)` | Phase 10 | Single registration point, explicit ordering |
| 14 `_with_storage` closure wrappers spread across 6 handler files | `_wrap()` in Router | Phase 10 | Storage injection centralized |
| Manual command dispatch in MAIN_MENU and RESERVE_ACTION handlers | Commands intercepted by registration order before state handlers | Phase 10 | Dead code in menu.py/reserve.py (removed in Phase 11) |
| Registration order determined by call order in main.py | `register_all()` enforces forwarded → commands → states | Phase 10 | Order is explicit and tested |

**After Phase 10:**
- `bot/handlers/*.py` files still have `register_handlers()` functions (removed in Phase 11)
- `main.py` imports are simplified to just `from bot.router import Router`
- The manual command dispatch in `main_menu_handler` and `reserve_action_handler` becomes dead code

## Open Questions

1. **Should register_all() validate FSM_CONFIG coverage?**
   - What we know: FSM_CONFIG has 18 states; Router registers 17 state handlers + 1 forwarded handler. A validation check could assert no FSM_CONFIG state is missing a handler.
   - What's unclear: This adds startup complexity for a check that would only catch mistakes during development.
   - Recommendation: Skip validation in Phase 10. The explicit `states` list in `_register_states()` serves as a checklist. A count assertion (`assert len(states) == 17`) is sufficient.

2. **Should debtors.py "Обновить" handler be in commands pass or a separate pass?**
   - What we know: It's a text="Обновить" rule, stateless. It must be before state handlers to work from any state.
   - Recommendation: Include in `_register_commands()` pass. It's not a slash command but functionally behaves like one (global, stateless).

3. **auth_guard field — does Phase 10 use it at all?**
   - What we know: FSM_CONFIG auth_guard is `"any"`, `"seller"`, or `"admin"`. Auth is enforced inside handlers. The Router doesn't add any auth rule.
   - Recommendation: Router ignores `auth_guard` in Phase 10. Document this in router.py docstring. Phase 11 or 12 can revisit if needed.

## Sources

### Primary (HIGH confidence)
- Direct inspection of vkbottle 4.6.2 source (installed at `/Users/thecattest/things/projects/Tickets/.venv/lib/python3.14/site-packages/vkbottle/`)
  - `vkbottle/framework/labeler/base.py` — `load()` source confirmed
  - `vkbottle/dispatch/views/bot/message.py` — `handle_event()` source confirmed
  - `vkbottle/dispatch/rules/base.py` — `StateRule.check()` and `VBMLRule.check()` confirmed
  - `vkbottle/dispatch/handlers.py` — `FromFuncHandler.filter()` confirmed
- Direct codebase read of all 7 handler files: exact function signatures, current closure patterns
- `bot/fsm/config.py` — Phase 9 output: FSM_CONFIG with 18 states confirmed
- `bot/fsm/states.py` — BotState enum: 18 states confirmed
- `bot/main.py` — current 7 `register_handlers()` calls confirmed
- Live Python session verifying handler count, ordering, and `labeler.load()` behavior

### Secondary (MEDIUM confidence)
- N/A — all findings from direct codebase and library source inspection

### Tertiary (LOW confidence)
- N/A

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all from direct vkbottle 4.6.2 source inspection and installed package
- Architecture: HIGH — dispatch mechanism verified by reading vkbottle internals; ordering prototype tested in live Python session
- Pitfalls: HIGH — derived from reading actual handler files and import chains

**Research date:** 2026-02-19
**Valid until:** Stable until vkbottle major version change; valid for all Phase 10 planning

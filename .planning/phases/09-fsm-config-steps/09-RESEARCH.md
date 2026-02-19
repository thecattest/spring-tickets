# Phase 9: FSM Config + Steps - Research

**Researched:** 2026-02-19
**Domain:** Python dataclasses, typed results, declarative config, code deduplication
**Confidence:** HIGH

## Summary

Phase 9 creates two new files: `bot/fsm/config.py` (declarative per-state FSM configuration) and `bot/steps.py` (three shared input primitives). Both files are consumed by Phase 10 (Router reads the config) and Phase 11 (handlers call the steps). Nothing in the existing codebase changes in this phase.

The duplication problem is concrete and measurable: row input validation appears in 4 handlers with identical parse+validate logic (113 lines total, ~28 lines each). Seat input parsing appears in 4 handlers with shared layout validation but diverging downstream checks (availability vs. membership vs. deferred). Confirmation yes/no appears in 3 handlers with the same three-branch structure.

The `handle_row_input()` step is cleanest to extract: all 4 row handlers do the same thing — int parse, `is_valid_row()`, store `current_row`, respond with seat count prompt. The step returns a `RowResult` dataclass. The handler then calls `storage.set(...)` to transition state — the step does NOT set state, it only validates input and returns a result.

The `handle_seat_input()` step is parameterized by mode because the three flows have different validation needs after layout check. A `mode` parameter (`"availability"`, `"membership"`, `"layout_only"`) controls which secondary checks run.

The `handle_confirmation()` step extracts the three-branch structure used identically in DELETION_CONFIRM, CANCEL_CONFIRM, and RESERVE_REMOVE_CONFIRM. It returns `Optional[bool]`: `True` for confirm, `False` for cancel, `None` for unknown input (re-show keyboard).

The FSM config is a dict mapping `BotState` members to `StateConfig` dataclasses. The config is read by Phase 10's Router. Phase 9 only defines it — no registration logic belongs here.

**Primary recommendation:** Define `RowResult`, `SeatResult`, and `StateConfig` as `@dataclass` (not `TypedDict` or `NamedTuple`) since they need optional fields and possible future methods. Use `Literal` for `mode` parameter. Keep steps pure (no storage access, no `message.answer` calls) so they are trivially testable.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `dataclasses` | stdlib (Python 3.7+) | `RowResult`, `SeatResult`, `StateConfig` | Zero overhead, type-checkable, clean `__repr__` |
| `typing.Literal` | stdlib (Python 3.8+) | Mode parameter type for `handle_seat_input` | Constrains to exact string values; IDE checks |
| `typing.Optional` | stdlib | Return type of `handle_confirmation` | `Optional[bool]` expresses None=unknown input clearly |
| `enum.StrEnum` | stdlib (Python 3.11+) | Already used in `BotState` via `BaseStateGroup` | Consistent with Phase 8 foundation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses.field` | stdlib | Default values in StateConfig (e.g., `validators: list = field(default_factory=list)`) | Complex defaults in dataclass |
| `typing.Callable` | stdlib | `handler` field type in `StateConfig` | Reference to async handler functions |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@dataclass` | `TypedDict` | TypedDict is better for dicts but not for objects with potential methods; dataclass is the right tool |
| `@dataclass` | `NamedTuple` | NamedTuple is immutable by default; StateConfig may need mutable optional fields |
| `Literal` mode param | `bool` flags | Multiple `bool` flags (check_availability=True, check_membership=False) is more error-prone than a single `Literal` |

**Installation:**
```bash
# No new packages required - all stdlib
```

## Architecture Patterns

### Recommended Project Structure
```
bot/
├── fsm/
│   ├── __init__.py
│   ├── states.py      # Existing: BotState enum (unchanged)
│   ├── storage.py     # Existing: RedisStorage (unchanged)
│   └── config.py      # NEW (Phase 9-01): declarative FSM state config dict
├── steps.py           # NEW (Phase 9-02): handle_row_input, handle_seat_input, handle_confirmation
└── handlers/          # Unchanged in Phase 9
```

### Pattern 1: RowResult dataclass
**What:** Typed result from `handle_row_input()`. Success carries the validated row number. Failure carries an error message already formatted for `message.answer()`.
**When to use:** Everywhere a handler currently does the int-parse + `is_valid_row()` + respond pattern.

```python
# bot/steps.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class RowResult:
    ok: bool
    row: Optional[int] = None      # present when ok=True
    error_text: Optional[str] = None  # present when ok=False, ready for message.answer()


def handle_row_input(text: str) -> RowResult:
    """
    Validate row number input. Pure function — no side effects.

    Returns RowResult with ok=True and row set, or ok=False with error_text set.
    Caller sends error_text to user if ok=False.
    """
    from bot.utils.layout import is_valid_row, get_row_range
    from bot import texts

    stripped = text.strip()
    try:
        row = int(stripped)
    except ValueError:
        min_row, max_row = get_row_range()
        return RowResult(ok=False, error_text=texts.ERR_INVALID_ROW_FORMAT.format(
            min_row=min_row, max_row=max_row
        ))

    if not is_valid_row(row):
        min_row, max_row = get_row_range()
        return RowResult(ok=False, error_text=texts.ERR_INVALID_ROW.format(
            min_row=min_row, max_row=max_row
        ))

    return RowResult(ok=True, row=row)
```

**Handler usage pattern (after migration in Phase 11):**
```python
async def awaiting_row_handler(message: Message, storage: RedisStorage):
    result = handle_row_input(message.text)
    if not result.ok:
        await message.answer(result.error_text)
        return
    # ... store result.row, transition state
```

### Pattern 2: SeatResult dataclass
**What:** Typed result from `handle_seat_input()`. Mode controls which validations run beyond layout check.
**When to use:** All four seat-input handlers (AWAITING_SEATS, DELETING_SEATS, RESERVE_ADDING_SEATS, RESERVE_REMOVING_SEATS).

```python
# bot/steps.py
from typing import Literal, List, Optional

@dataclass
class SeatResult:
    ok: bool
    seats: Optional[List[int]] = None   # present when ok=True
    error_text: Optional[str] = None    # present when ok=False, ready for message.answer()


def handle_seat_input(
    text: str,
    row: int,
    mode: Literal["layout_only", "availability", "membership"],
    reservation_id: Optional[int] = None,
) -> SeatResult:
    """
    Parse and validate seat input.

    mode="layout_only"   — parse + check seats are valid for the row (reserve flows)
    mode="availability"  — layout_only + check seats are not occupied (reservation add flow)
    mode="membership"    — layout_only + check seats belong to reservation, not PAID (deletion flow)

    reservation_id required when mode="membership".
    """
    ...
```

**Mode selection by flow:**

| Handler | mode | Why |
|---------|------|-----|
| `awaiting_seats_handler` (reservation) | `"availability"` | Must verify seats are free before booking |
| `deleting_seats_handler` (deletion) | `"membership"` | Must verify seats belong to this reservation and aren't PAID |
| `reserve_adding_seats_handler` | `"layout_only"` | Availability deferred to `db.add_reserve()` (handles conflicts there) |
| `reserve_removing_seats_handler` | `"layout_only"` | No availability check needed; just check layout validity |

**Critical distinction for availability mode:** The existing `awaiting_seats_handler` does two-phase availability checking: first a manual loop through `db.get_seat_assignment()`, then catches `db.SeatOccupiedError` from `db.add_seats_to_reservation()`. The step only handles the pre-check (loop). The DB-level conflict is caught by the handler after calling `db.add_seats_to_reservation()`.

### Pattern 3: handle_confirmation()
**What:** Extracts the identical three-branch "Подтвердить/Отмена/else" structure.
**When to use:** DELETION_CONFIRM, CANCEL_CONFIRM, RESERVE_REMOVE_CONFIRM states.

```python
# bot/steps.py
def handle_confirmation(text: str) -> Optional[bool]:
    """
    Parse confirmation button input.

    Returns:
        True   — "Подтвердить" pressed
        False  — "Отмена" pressed
        None   — unknown input (re-show keyboard)
    """
    from bot.constants import Btn
    stripped = text.strip()
    if stripped == Btn.CONFIRM:
        return True
    if stripped == Btn.CANCEL:
        return False
    return None
```

**Handler usage pattern:**
```python
async def deletion_confirm_handler(message: Message, storage: RedisStorage):
    confirmed = handle_confirmation(message.text)
    if confirmed is None:
        await message.answer(texts.PROMPT_SELECT_ACTION, keyboard=confirmation_keyboard())
        return
    if confirmed:
        # ... do deletion
    else:
        await message.answer(texts.MSG_CANCELLED_BRIEF, keyboard=get_empty_keyboard())
        # ... show main menu
```

### Pattern 4: StateConfig dataclass (FSM Config)
**What:** One `StateConfig` instance per `BotState`. The full mapping dict is `FSM_CONFIG`.
**When to use:** Phase 10 Router reads this to auto-register handlers. Phase 12 reads `back_state` for /cancel navigation.

```python
# bot/fsm/config.py
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Literal
from bot.fsm.states import BotState


@dataclass
class StateConfig:
    state: BotState
    handler: Callable                              # the async handler function (imported lazily)
    input_type: Literal["text", "forwarded"]       # what triggers this handler
    auth_guard: Literal["any", "seller", "admin"]  # who is allowed
    back_state: Optional[BotState] = None          # Phase 12: /cancel navigates here
    forward_states: List[BotState] = field(default_factory=list)  # informational only


FSM_CONFIG: dict[BotState, StateConfig] = {
    BotState.IDLE: StateConfig(
        state=BotState.IDLE,
        handler=...,       # forwarded_message_handler
        input_type="forwarded",
        auth_guard="any",
        back_state=None,   # IDLE has no back state
    ),
    BotState.AWAITING_ROW: StateConfig(
        state=BotState.AWAITING_ROW,
        handler=...,       # awaiting_row_handler
        input_type="text",
        auth_guard="seller",
        back_state=BotState.IDLE,   # NOTE: see Open Questions — ambiguous
        forward_states=[BotState.AWAITING_SEATS],
    ),
    # ... all 16 states
}
```

### Anti-Patterns to Avoid

- **Steps that call `message.answer()`:** Steps must be pure functions returning result objects. The handler calls `message.answer()` based on the result. This keeps steps testable without mocking VK API.
- **Steps that call `storage.set()`:** State transitions are the handler's job, not the step's. Steps validate input only.
- **FSM config circular imports:** `config.py` must import handler functions to populate `handler:` fields. Handler files import from `bot.utils`, `bot.fsm.states`, `bot.keyboards`. None import from `bot.fsm.config`. So `config.py` imports from handlers — this is one-directional and safe. Use lazy imports inside `StateConfig` construction if needed.
- **Putting business logic in steps:** `handle_seat_input` with `mode="availability"` checks if seats are occupied. It does NOT call `db.add_seats_to_reservation()`. The handler does that. Steps only validate, handlers act.
- **`RowResult` sending error messages:** The step returns `error_text` as a string. The handler sends it. This pattern is consistent with `texts.py` — strings are data, sending is handler responsibility.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Typed result objects | Dict with "ok", "error" keys | `@dataclass` | Static type checking, IDE autocomplete, `__repr__` |
| Mode-based validation | Multiple boolean flags | `Literal` type | Single source of truth for valid mode values |
| Confirmation parsing | Inline `if text == "Подтвердить"` in every handler | `handle_confirmation()` | `Btn.CONFIRM` is already defined; centralizes the string reference |

**Key insight:** The steps are not about DRY for its own sake — they are about creating a stable interface that Phase 10 (Router) and Phase 11 (Handler Migration) can depend on. Once `handle_row_input()` exists with a known signature, Phase 11 handler migration becomes mechanical substitution.

## Common Pitfalls

### Pitfall 1: Steps that do too much (returning after `message.answer`)
**What goes wrong:** The step calls `message.answer()` itself and returns a bool. Handler can't customize the error message or keyboard.
**Why it happens:** Seems more convenient to handle everything in one function.
**How to avoid:** Return `RowResult(ok=False, error_text=...)`. Handler calls `await message.answer(result.error_text)`. This keeps steps testable (no `Message` object needed) and allows handlers to add keyboard context to error responses.
**Warning signs:** If `handle_row_input()` signature includes `message: Message`, scope has leaked.

### Pitfall 2: FSM config circular import
**What goes wrong:** `bot/fsm/config.py` imports handler functions; handler files import from `bot/fsm/config.py` for state constants.
**Why it happens:** Handlers need `BotState` from `bot/fsm/states.py`, and `config.py` needs handler functions.
**How to avoid:** Handler files import from `bot.fsm.states` (not `bot.fsm.config`). `config.py` imports from handler files. This is one-directional: `config.py` → `handlers/`, `handlers/` → `fsm/states.py`. No cycle. Verify with `python -c "from bot.fsm.config import FSM_CONFIG"` after creation.
**Warning signs:** `ImportError: cannot import name 'FSM_CONFIG'` at startup.

### Pitfall 3: AWAITING_ROW back_state ambiguity
**What goes wrong:** `BotState.AWAITING_ROW` is reached from two entry points — forwarded message (new reservation, back = IDLE) and SEAT_ADDITION_MENU "Добавить еще" (back = SEAT_ADDITION_MENU). A single `back_state` field can't express both.
**Why it happens:** Same state, two flows. Phase 9 defines the config; Phase 12 uses it for /cancel navigation.
**How to avoid:** For Phase 9, use `back_state=BotState.IDLE` as the default. Document the ambiguity. Phase 12 will resolve it with context-based back navigation (checking `from_main_menu` in payload). Do NOT block Phase 9 delivery on this.
**Warning signs:** This is a known concern already flagged in the phase context. The `back_state` field in `StateConfig` is informational for Phase 12 — it is not used in Phase 9 or Phase 10.

### Pitfall 4: `handle_seat_input` doing too much availability checking
**What goes wrong:** The `availability` mode calls `db.add_seats_to_reservation()` inside the step, trying to be clever and do both check and action. Now the step has side effects.
**Why it happens:** "Might as well do it in one call."
**How to avoid:** `mode="availability"` calls `db.get_seat_assignment(row, seat)` for each seat and returns occupied seats list in `SeatResult.occupied`. The handler sees `SeatResult(ok=False, occupied=[...])` and formats the error. Actual DB write (`db.add_seats_to_reservation`) stays in the handler.
**Warning signs:** If `SeatResult` has a field like `assignments_created`, the step has overstepped.

### Pitfall 5: `handle_confirmation` comparing raw strings
**What goes wrong:** `if text.strip() == "Подтвердить"` hardcodes the string. Phase 8 created `Btn.CONFIRM` precisely to avoid this.
**Why it happens:** "It's a small function, who cares."
**How to avoid:** `from bot.constants import Btn` and compare to `Btn.CONFIRM`, `Btn.CANCEL`. If the button label changes, it changes in one place.

### Pitfall 6: Importing handlers at module level in config.py
**What goes wrong:** `from bot.handlers.reservation import awaiting_row_handler` at top of `config.py` triggers import of `reservation.py`, which imports `menu.py` for `show_main_menu`, which imports `payment.py` for `start_payment_flow`. Import chain creates cycles or order issues.
**Why it happens:** Natural to import at module level.
**How to avoid:** Use string module paths or callable references with lazy import. Simplest approach: populate `handler` fields after all imports resolve, or use `typing.TYPE_CHECKING` guard for type hints only and populate the dict at module level after defining a local import helper. Alternatively, `handler` field can be `None` in Phase 9 — Phase 10 wires the handlers in. This avoids the problem entirely.
**Warning signs:** `ImportError` or `AttributeError: module 'bot.handlers.reservation' has no attribute 'awaiting_row_handler'` at import time.

## Code Examples

### Complete RowResult and handle_row_input()
```python
# bot/steps.py
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RowResult:
    ok: bool
    row: Optional[int] = None
    error_text: Optional[str] = None


def handle_row_input(text: str) -> RowResult:
    """
    Validate row number input. Pure function — no side effects.

    Returns RowResult(ok=True, row=N) or RowResult(ok=False, error_text="...").
    Caller sends error_text to user if ok=False.
    """
    from bot.utils.layout import is_valid_row, get_row_range
    from bot import texts

    stripped = text.strip()
    try:
        row = int(stripped)
    except ValueError:
        min_row, max_row = get_row_range()
        return RowResult(
            ok=False,
            error_text=texts.ERR_INVALID_ROW_FORMAT.format(min_row=min_row, max_row=max_row),
        )

    if not is_valid_row(row):
        min_row, max_row = get_row_range()
        return RowResult(
            ok=False,
            error_text=texts.ERR_INVALID_ROW.format(min_row=min_row, max_row=max_row),
        )

    return RowResult(ok=True, row=row)
```

### SeatResult and handle_seat_input() — availability mode
```python
# bot/steps.py (continued)
from typing import List, Literal


@dataclass
class SeatResult:
    ok: bool
    seats: Optional[List[int]] = None
    error_text: Optional[str] = None


def handle_seat_input(
    text: str,
    row: int,
    mode: Literal["layout_only", "availability", "membership"],
    reservation_id: Optional[int] = None,
) -> SeatResult:
    """
    Parse and validate seat input.

    mode="layout_only":  parse + check valid for the row
    mode="availability": layout_only + check not occupied in DB
    mode="membership":   layout_only + check belong to reservation and not PAID
    """
    from bot.utils.seat_parser import parse_seats, SeatParseError
    from bot.utils.layout import is_valid_seat, get_seat_count
    from bot import texts

    # Step 1: Parse
    try:
        seats = parse_seats(text.strip())
    except SeatParseError as e:
        return SeatResult(ok=False, error_text=texts.ERR_PARSE_INPUT.format(error=str(e)))

    # Step 2: Layout validation (all modes)
    seat_count = get_seat_count(row)
    invalid = [s for s in seats if not is_valid_seat(row, s)]
    if invalid:
        return SeatResult(
            ok=False,
            error_text=texts.ERR_INVALID_SEATS.format(
                seats=", ".join(map(str, invalid)),
                row=row,
                seat_count=seat_count,
            ),
        )

    # Step 3: Mode-specific validation
    if mode == "layout_only":
        return SeatResult(ok=True, seats=seats)

    if mode == "availability":
        from bot.utils import db
        occupied = []
        for seat in seats:
            assignment = db.get_seat_assignment(row, seat)
            if assignment:
                occupied.append((seat, assignment))
        if occupied:
            from models.base import SeatStatus
            error_lines = ["Места уже заняты:"]
            for seat, assignment in occupied:
                if assignment.status == SeatStatus.RESERVED:
                    status_text = "Резерв"
                    detail = assignment.note or "без комментария"
                else:
                    status_text = "Бронь" if assignment.status == SeatStatus.BOOKED else "Оплачено"
                    try:
                        res_seats = db.get_reservation_seats(assignment.reservation_id)
                        detail = f"бронь #{assignment.reservation_id}, всего мест: {len(res_seats)}"
                    except Exception:
                        detail = f"бронь #{assignment.reservation_id}"
                error_lines.append(f"• Ряд {row}, место {seat} — {status_text} ({detail})")
            error_lines.append("\nВведите другие места:")
            return SeatResult(ok=False, error_text="\n".join(error_lines))
        return SeatResult(ok=True, seats=seats)

    if mode == "membership":
        from bot.utils import db
        from models.base import SeatStatus
        all_reservation_seats = db.get_reservation_seats(reservation_id)
        seat_map = {(s.row_number, s.seat_number): s for s in all_reservation_seats}

        not_in_reservation = [s for s in seats if (row, s) not in seat_map]
        if not_in_reservation:
            return SeatResult(
                ok=False,
                error_text=texts.MSG_SEATS_NOT_IN_BOOKING.format(
                    seats=", ".join(map(str, not_in_reservation))
                ),
            )

        paid_seats = [s for s in seats if seat_map[(row, s)].status == SeatStatus.PAID]
        if paid_seats:
            return SeatResult(
                ok=False,
                error_text=texts.MSG_SEATS_ALREADY_PAID.format(
                    seats=", ".join(map(str, paid_seats))
                ),
            )

        return SeatResult(ok=True, seats=seats)

    raise ValueError(f"Unknown mode: {mode}")
```

### handle_confirmation()
```python
# bot/steps.py (continued)

def handle_confirmation(text: str) -> Optional[bool]:
    """
    Parse confirmation button input.

    Returns True for Btn.CONFIRM, False for Btn.CANCEL, None for unknown.
    """
    from bot.constants import Btn
    stripped = text.strip()
    if stripped == Btn.CONFIRM:
        return True
    if stripped == Btn.CANCEL:
        return False
    return None
```

### StateConfig dataclass (FSM config skeleton)
```python
# bot/fsm/config.py
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Literal, Any
from bot.fsm.states import BotState


@dataclass
class StateConfig:
    state: BotState
    input_type: Literal["text", "forwarded", "button"]
    auth_guard: Literal["any", "seller", "admin"]
    handler: Optional[Callable] = None            # wired by Phase 10 Router or set here
    back_state: Optional[BotState] = None         # Phase 12: /cancel goes here
    forward_states: List[BotState] = field(default_factory=list)  # for documentation


# NOTE: handler fields left as None in Phase 9 to avoid circular imports.
# Phase 10 Router wires handlers into the config or reads handler references directly.
FSM_CONFIG: dict[BotState, StateConfig] = {

    # --- Idle ---
    BotState.IDLE: StateConfig(
        state=BotState.IDLE,
        input_type="forwarded",
        auth_guard="any",
        back_state=None,
    ),

    # --- Reservation flow ---
    BotState.AWAITING_ROW: StateConfig(
        state=BotState.AWAITING_ROW,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.IDLE,        # ambiguous — see Open Questions
        forward_states=[BotState.AWAITING_SEATS],
    ),
    BotState.AWAITING_SEATS: StateConfig(
        state=BotState.AWAITING_SEATS,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.AWAITING_ROW,
        forward_states=[BotState.SEAT_ADDITION_MENU],
    ),
    BotState.SEAT_ADDITION_MENU: StateConfig(
        state=BotState.SEAT_ADDITION_MENU,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.AWAITING_ROW,
        forward_states=[BotState.AWAITING_ROW, BotState.MAIN_MENU, BotState.IDLE],
    ),

    # --- Main menu ---
    BotState.MAIN_MENU: StateConfig(
        state=BotState.MAIN_MENU,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.IDLE,
        forward_states=[
            BotState.AWAITING_ROW, BotState.DELETING_ROW,
            BotState.CANCEL_CONFIRM, BotState.PAYMENT_QUANTITY,
        ],
    ),

    # --- Deletion flow ---
    BotState.DELETING_ROW: StateConfig(
        state=BotState.DELETING_ROW,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.MAIN_MENU,
        forward_states=[BotState.DELETING_SEATS],
    ),
    BotState.DELETING_SEATS: StateConfig(
        state=BotState.DELETING_SEATS,
        input_type="text",
        auth_guard="seller",
        back_state=BotState.DELETING_ROW,
        forward_states=[BotState.DELETION_CONFIRM],
    ),
    BotState.DELETION_CONFIRM: StateConfig(
        state=BotState.DELETION_CONFIRM,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.DELETING_ROW,
        forward_states=[BotState.MAIN_MENU],
    ),
    BotState.CANCEL_CONFIRM: StateConfig(
        state=BotState.CANCEL_CONFIRM,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.MAIN_MENU,
        forward_states=[BotState.IDLE, BotState.MAIN_MENU],
    ),
    BotState.CONTEXT_SWITCH_CONFIRM: StateConfig(
        state=BotState.CONTEXT_SWITCH_CONFIRM,
        input_type="button",
        auth_guard="any",
        back_state=None,  # restores original_state from payload
        forward_states=[BotState.MAIN_MENU, BotState.AWAITING_ROW],
    ),

    # --- Payment flow ---
    BotState.PAYMENT_QUANTITY: StateConfig(
        state=BotState.PAYMENT_QUANTITY,
        input_type="button",
        auth_guard="seller",
        back_state=BotState.MAIN_MENU,
        forward_states=[BotState.MAIN_MENU],
    ),

    # --- Reserve flow (admin only) ---
    BotState.RESERVE_ACTION: StateConfig(
        state=BotState.RESERVE_ACTION,
        input_type="button",
        auth_guard="admin",
        back_state=BotState.IDLE,
        forward_states=[BotState.RESERVE_ADDING_ROW, BotState.RESERVE_REMOVING_ROW],
    ),
    BotState.RESERVE_ADDING_ROW: StateConfig(
        state=BotState.RESERVE_ADDING_ROW,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ACTION,
        forward_states=[BotState.RESERVE_ADDING_SEATS],
    ),
    BotState.RESERVE_ADDING_SEATS: StateConfig(
        state=BotState.RESERVE_ADDING_SEATS,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ADDING_ROW,
        forward_states=[BotState.RESERVE_COMMENT],
    ),
    BotState.RESERVE_COMMENT: StateConfig(
        state=BotState.RESERVE_COMMENT,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ADDING_ROW,
        forward_states=[BotState.RESERVE_ACTION],
    ),
    BotState.RESERVE_REMOVING_ROW: StateConfig(
        state=BotState.RESERVE_REMOVING_ROW,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_ACTION,
        forward_states=[BotState.RESERVE_REMOVING_SEATS],
    ),
    BotState.RESERVE_REMOVING_SEATS: StateConfig(
        state=BotState.RESERVE_REMOVING_SEATS,
        input_type="text",
        auth_guard="admin",
        back_state=BotState.RESERVE_REMOVING_ROW,
        forward_states=[BotState.RESERVE_REMOVE_CONFIRM],
    ),
    BotState.RESERVE_REMOVE_CONFIRM: StateConfig(
        state=BotState.RESERVE_REMOVE_CONFIRM,
        input_type="button",
        auth_guard="admin",
        back_state=BotState.RESERVE_REMOVING_ROW,
        forward_states=[BotState.RESERVE_ACTION],
    ),
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Row validation duplicated in 4 handlers | `handle_row_input()` pure function | Phase 9 | ~112 lines collapsed to 1 call site per handler |
| Seat parse+validate duplicated in 4 handlers | `handle_seat_input(mode=...)` | Phase 9 | Diverging validation logic made explicit via mode param |
| Confirmation if/elif/else in 3 handlers | `handle_confirmation()` | Phase 9 | `Btn.CONFIRM`/`Btn.CANCEL` referenced once |
| FSM behavior scattered across 7 handler files | `FSM_CONFIG` dict | Phase 9 | Phase 10 Router reads one data structure |

**Deprecated/outdated after Phase 11:**
- Inline `try: row = int(text) except ValueError:` blocks in handlers
- Inline `[s for s in seats if not is_valid_seat(row, s)]` in handlers
- Inline `if text == "Подтвердить": ... elif text == "Отмена":` blocks in 3 handlers

## Open Questions

1. **AWAITING_ROW back_state is ambiguous**
   - What we know: `AWAITING_ROW` is reached from two entry points — (a) forwarded message handler (new reservation, back = IDLE) and (b) `SEAT_ADDITION_MENU` "Добавить еще" button (back = SEAT_ADDITION_MENU). The FSM_CONFIG `back_state` field accepts one value.
   - What's unclear: Phase 12 needs to resolve this — `/cancel` in AWAITING_ROW should go to different states depending on how the user got there. This cannot be fully resolved by static config alone.
   - Recommendation: In Phase 9, set `back_state=BotState.IDLE` as the conservative default. Document the ambiguity in a comment. Phase 12 resolves it by inspecting `from_main_menu` in storage payload at /cancel time.

2. **handler field in StateConfig — None or real references**
   - What we know: Populating handler fields with actual function references in config.py risks circular imports (config imports handlers; handlers currently don't import config, but Phase 10 may add that).
   - What's unclear: Phase 10 design (not yet researched) determines whether the Router reads `StateConfig.handler` or builds its own handler mapping from the config.
   - Recommendation: For Phase 9, leave `handler=None` in all `StateConfig` instances. Add a `# TODO Phase 10: wire handlers` comment. Phase 10 research will clarify whether the Router populates handlers or the config does.

3. **auth_guard "seller" vs "any" for forwarded message handler**
   - What we know: The forwarded message handler (IDLE entry) is called by any user who forwards a message. The handler itself checks `db.get_seller_id()` which can raise if the user isn't registered.
   - What's unclear: Whether auth should be enforced at the Router level (Phase 10) or stay in the handler.
   - Recommendation: Set `auth_guard="any"` for IDLE/forwarded handler in Phase 9 config. Phase 10 decides enforcement strategy.

## Sources

### Primary (HIGH confidence)
- Direct codebase read of all 7 handler files — duplication patterns counted precisely
- `bot/fsm/states.py` — all 16 BotState members enumerated
- `bot/utils/seat_parser.py` — `parse_seats()` signature and `SeatParseError` confirmed
- `bot/utils/layout.py` — `is_valid_row()`, `is_valid_seat()`, `get_seat_count()`, `get_row_range()` signatures confirmed
- `bot/texts.py` — all relevant error/prompt constants confirmed present
- `bot/constants.py` — `Btn.CONFIRM`, `Btn.CANCEL` confirmed present
- Python 3.14 stdlib — `dataclasses`, `typing.Literal`, `typing.Optional` confirmed available

### Secondary (MEDIUM confidence)
- N/A — all findings from direct codebase audit

### Tertiary (LOW confidence)
- N/A

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, no third-party deps
- Architecture: HIGH — based on complete codebase audit, duplication counted line by line
- Pitfalls: HIGH — circular import risk is real (confirmed by reading import chains), back_state ambiguity is pre-flagged in phase context

**Research date:** 2026-02-19
**Valid until:** Stable for this codebase — no third-party churn; valid until Phase 11 migration changes handler signatures

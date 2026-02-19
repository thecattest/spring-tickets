# Phase 12: Navigation UX - Research

**Researched:** 2026-02-19
**Domain:** FSM navigation — /cancel back-step, /exit hard-reset, early row validation
**Confidence:** HIGH

## Summary

Phase 12 adds proper step-back navigation (/cancel → one step back), a distinct hard-reset command (/exit → IDLE), and early row validation that blocks useless seat prompts when a row has no relevant seats.

The infrastructure is already in place: `FSM_CONFIG` (bot/fsm/config.py) has a `back_state` field on every `StateConfig` entry, already populated for all 18 states except two special cases (`IDLE` and `CONTEXT_SWITCH_CONFIRM` are `None`). The `cancel_handler` in `bot/handlers/commands.py` currently does a full `storage.delete()` — it needs to be changed to read the current state's `back_state` from `FSM_CONFIG` and `storage.set()` to that state instead. The `exit_handler` already exists and does the correct hard-reset; no changes needed there. Early row validation requires new `db.py` helper functions and insertion of validation logic into the four row-input handlers: `awaiting_row_handler`, `deleting_row_handler`, `reserve_adding_row_handler`, `reserve_removing_row_handler`.

**Primary recommendation:** Change `cancel_handler` to read `FSM_CONFIG[current_state].back_state` and navigate there; for `None` back_states (IDLE, CONTEXT_SWITCH_CONFIRM) fall back to IDLE with the existing clear behavior. Add row-level seat availability check functions to `db.py` and call them before transitioning to the seats-input state.

## Complete BACK_MAP (All 18 States)

The single most critical deliverable for 12-01. The entire BACK_MAP must be defined before implementation begins. Here it is, derived directly from `bot/fsm/config.py` and the handler logic:

| State | back_state in config.py | Back behavior | Ambiguity? |
|-------|------------------------|---------------|------------|
| IDLE | None | No /cancel action (already idle) | None |
| AWAITING_ROW | `BotState.IDLE` (but NOTE below) | Context-dependent (see below) | **YES** |
| AWAITING_SEATS | `BotState.AWAITING_ROW` | Return to row input | None |
| SEAT_ADDITION_MENU | `BotState.AWAITING_ROW` | Return to row input | None |
| MAIN_MENU | `BotState.IDLE` | Clear state, back to IDLE | None |
| DELETING_ROW | `BotState.MAIN_MENU` | Return to main menu | None |
| DELETING_SEATS | `BotState.DELETING_ROW` | Return to row input | None |
| DELETION_CONFIRM | `BotState.DELETING_ROW` | Return to row input | None |
| CANCEL_CONFIRM | `BotState.MAIN_MENU` | Return to main menu | None |
| CONTEXT_SWITCH_CONFIRM | None | Hard reset to IDLE | None |
| PAYMENT_QUANTITY | `BotState.MAIN_MENU` | Return to main menu | None |
| RESERVE_ACTION | `BotState.IDLE` | Clear state, back to IDLE | None |
| RESERVE_ADDING_ROW | `BotState.RESERVE_ACTION` | Return to reserve action menu | None |
| RESERVE_ADDING_SEATS | `BotState.RESERVE_ADDING_ROW` | Return to row input | None |
| RESERVE_COMMENT | `BotState.RESERVE_ADDING_ROW` | Return to row input | None |
| RESERVE_REMOVING_ROW | `BotState.RESERVE_ACTION` | Return to reserve action menu | None |
| RESERVE_REMOVING_SEATS | `BotState.RESERVE_REMOVING_ROW` | Return to row input | None |
| RESERVE_REMOVE_CONFIRM | `BotState.RESERVE_REMOVING_ROW` | Return to row input | None |

### Resolving the AWAITING_ROW Ambiguity

`AWAITING_ROW` is reached from two distinct points:

1. **From IDLE** (new client, no existing reservation): `forwarded_message_handler` creates a reservation and sets `AWAITING_ROW` with `from_main_menu` absent or `False`.
2. **From MAIN_MENU** ("Добавить" button or context switch): `main_menu_handler` and `context_switch_handler` set `AWAITING_ROW` preserving context with `from_main_menu=True`.
3. **From SEAT_ADDITION_MENU** ("Добавить еще" button): `seat_addition_menu_handler` sets `AWAITING_ROW` preserving context with `from_main_menu` already set.

**Resolution**: The `from_main_menu` flag already stored in `StatePeer.payload` provides the discriminator:

- `from_main_menu=True` → back_state is `MAIN_MENU` (restore main menu with reservation context)
- `from_main_menu=False` or absent → back_state is `IDLE` (clear state, user was creating from scratch)

`cancel_handler` must read `context.get("from_main_menu")` when current state is `AWAITING_ROW`, then:
- If `True`: `storage.set(user_id, BotState.MAIN_MENU, **context)` + show main menu message
- If `False`/absent: `storage.delete(user_id)` + show cancel message

For the `MAIN_MENU` case, `show_main_menu()` requires `message`, `storage`, `reservation_id`, `vk_user_id`, `buyer_display_name`, `buyer_vk_api_id` — all available in context as `reservation_id`, `buyer_vk_user_id`, `buyer_vk_api_id`, `buyer_display_name`.

### CONTEXT_SWITCH_CONFIRM back_state = None

`CONTEXT_SWITCH_CONFIRM` already has a "Нет" button that restores original state in `context_switch_handler`. `/cancel` during this state should behave like "Нет" — restore original state if available, or clear to IDLE. This is identical to the existing `elif text == Btn.NO` branch in `context_switch_handler`. The safest implementation: when `cancel_handler` sees `back_state=None` and current state is `CONTEXT_SWITCH_CONFIRM`, restore `original_state`/`original_context` from payload, mirroring the "Нет" branch.

## Standard Stack

No new libraries. All tooling is already present.

### Core (already installed)
| Component | Version | Purpose |
|-----------|---------|---------|
| vkbottle | existing | VK bot framework, FSM dispatch |
| Redis / RedisStorage | existing | FSM state + payload storage |
| SQLAlchemy | existing | DB queries for early row validation |
| bot/fsm/config.py | Phase 9 | `FSM_CONFIG` dict with `back_state` fields |
| bot/fsm/storage.py | Phase 9 | `get_context()`, `set()`, `delete()` |
| bot/handlers/commands.py | Phase 10 | `cancel_handler`, `exit_handler` |

## Architecture Patterns

### Pattern 1: cancel_handler reads FSM_CONFIG

**What:** `cancel_handler` gets current state from `storage.get()`, looks up `FSM_CONFIG[state].back_state`, then either navigates back or clears.

**Exact implementation:**
```python
# bot/handlers/commands.py
async def cancel_handler(message: Message, storage):
    logger.info(f"User {message.from_id} sent /cancel")
    try:
        state_peer = await storage.get(message.from_id)

        if state_peer is None:
            # Already idle
            await message.answer(texts.MSG_CANCEL_ALREADY_IDLE, keyboard=commands_keyboard())
            return

        current_state = state_peer.state  # BotState enum value
        # Resolve actual BotState enum member from string stored in Redis
        # storage.get() returns StatePeer; state is stored as "BotState:awaiting_row"
        # Must normalize to BotState enum member for FSM_CONFIG lookup

        config = FSM_CONFIG.get(current_state)
        back = config.back_state if config else None

        # Special case: AWAITING_ROW ambiguity — check from_main_menu
        if current_state == BotState.AWAITING_ROW:
            from_main_menu = state_peer.payload.get("from_main_menu", False)
            if from_main_menu:
                back = BotState.MAIN_MENU
            else:
                back = None  # fall through to clear

        if back is None:
            # No back state — hard clear
            await storage.delete(message.from_id)
            await message.answer(texts.MSG_CANCEL_FULL, keyboard=commands_keyboard())
        else:
            # Navigate back to back_state, preserving payload
            await storage.set(message.from_id, back, **state_peer.payload)
            await _send_back_state_prompt(message, back, state_peer.payload)
    except Exception as e:
        logger.error(f"Error in /cancel: {e}")
        await message.answer(texts.MSG_CANCELLED)
```

**Key detail — state string format:** `storage.get()` returns a `StatePeer`. Its `.state` attribute is stored as a string like `"BotState:awaiting_row"` (the `vkbottle` `BaseStateGroup` string representation). `FSM_CONFIG` is keyed by `BotState` enum members. The lookup `FSM_CONFIG.get(state_peer.state)` will NOT work directly. Need to convert: iterate `FSM_CONFIG` keys or use `BotState(state_peer.state.split(":")[-1])`.

Verified pattern in existing code — `context_switch_handler` does exactly this:
```python
# bot/handlers/menu.py line 307
restored_state = BotState(original_state.split(":")[-1])
```

### Pattern 2: Sending the back-state prompt

When `/cancel` navigates back, it must show the appropriate prompt for the restored state. A lookup dict approach:

```python
# Map back_state → (message_text, keyboard_fn)
_BACK_PROMPTS = {
    BotState.MAIN_MENU: (None, main_menu_keyboard),  # use show_main_menu helper
    BotState.AWAITING_ROW: (texts.PROMPT_ENTER_ROW, get_empty_keyboard),
    BotState.DELETING_ROW: (texts.PROMPT_ENTER_ROW_DELETE, get_empty_keyboard),
    BotState.RESERVE_ACTION: (texts.MSG_RESERVE_ACTION_HEADER, reserve_action_keyboard),
    BotState.RESERVE_ADDING_ROW: (texts.PROMPT_ENTER_ROW, get_empty_keyboard),
    BotState.RESERVE_REMOVING_ROW: (texts.PROMPT_ENTER_ROW, get_empty_keyboard),
    # ... etc
}
```

For `MAIN_MENU` back, call `show_main_menu()` with context data instead of a plain `message.answer()`.

### Pattern 3: Early Row Validation

**What:** After `handle_row_input()` succeeds (row is valid in layout), check if that row has relevant seats for the current operation before transitioning to the seats state.

**Four cases that need early validation:**

| Handler | State | Validation needed | DB query |
|---------|-------|-------------------|----------|
| `awaiting_row_handler` | `AWAITING_ROW` | Row has available (free) seats | `get_available_seats_in_row(row)` |
| `deleting_row_handler` | `DELETING_ROW` | Row has booked seats in this reservation | `get_reservation_seats_in_row(reservation_id, row)` |
| `reserve_adding_row_handler` | `RESERVE_ADDING_ROW` | Row has free seats (any free seat) | `get_available_seats_in_row(row)` |
| `reserve_removing_row_handler` | `RESERVE_REMOVING_ROW` | Row has reserved (RESERVED status) seats | `get_reserved_seats_in_row(row)` |

**New db.py functions needed** (none exist currently):

```python
def get_available_seats_in_row(row: int) -> list[int]:
    """Return seat numbers in the row that are currently unoccupied."""
    with SessionLocal() as session:
        layout_seat_count = get_seat_count(row)  # from bot.utils.layout
        occupied_stmt = (
            select(SeatAssignment.seat_number)
            .where(SeatAssignment.row_number == row)
            .where(SeatAssignment.released_at.is_(None))
        )
        occupied = {r[0] for r in session.execute(occupied_stmt).all()}
        return [s for s in range(1, layout_seat_count + 1) if s not in occupied]

def get_reservation_seats_in_row(reservation_id: int, row: int) -> list[SeatAssignment]:
    """Return active SeatAssignments for this reservation in this row."""
    with SessionLocal() as session:
        stmt = (
            select(SeatAssignment)
            .where(SeatAssignment.reservation_id == reservation_id)
            .where(SeatAssignment.row_number == row)
            .where(SeatAssignment.released_at.is_(None))
        )
        return list(session.execute(stmt).scalars().all())

def get_reserved_seats_in_row(row: int) -> list[SeatAssignment]:
    """Return active RESERVED SeatAssignments in this row (no reservation_id)."""
    with SessionLocal() as session:
        stmt = (
            select(SeatAssignment)
            .where(SeatAssignment.row_number == row)
            .where(SeatAssignment.status == SeatStatus.RESERVED)
            .where(SeatAssignment.released_at.is_(None))
            .where(SeatAssignment.reservation_id.is_(None))
        )
        return list(session.execute(stmt).scalars().all())
```

**Insertion point in handlers:**
```python
# After handle_row_input() succeeds, before storage.set() to next state
# Example: awaiting_row_handler
result = handle_row_input(message.text)
if not result.ok:
    await message.answer(result.error_text)
    return
row = result.row

# NAV-03: early row validation
available = db.get_available_seats_in_row(row)
if not available:
    await message.answer(texts.ERR_ROW_NO_AVAILABLE_SEATS.format(row=row))
    return  # stay in AWAITING_ROW, re-prompt for row

# ... proceed to set AWAITING_SEATS
```

### Anti-Patterns to Avoid

- **Do not clear context on /cancel back-navigation.** The context (reservation_id, buyer info, from_main_menu) must be preserved in payload when calling `storage.set(user_id, back_state, **state_peer.payload)`. The back handler will need this context to show the correct prompt.
- **Do not import `show_main_menu` at module level in commands.py.** Use a local import inside `cancel_handler` to avoid circular imports (commands.py is low-level, show_main_menu is higher-level).
- **Do not add /exit registration again in router.py.** `/exit` is already registered in `_register_commands()` at line 175.
- **Do not change exit_handler.** It already does `storage.delete()` + `texts.MSG_EXIT_FULL`. This is the correct hard-reset behavior.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State enum lookup from string | custom state registry | `BotState(state_str.split(":")[-1])` | Already proven in context_switch_handler |
| Navigation history stack | custom history list | `back_state` field in FSM_CONFIG | Already architected — single-level back is enough |
| Early validation middleware | vkbottle middleware | db query + early return in handler | Handlers already own validation chain |

## Common Pitfalls

### Pitfall 1: BotState enum lookup from Redis string
**What goes wrong:** `FSM_CONFIG.get(state_peer.state)` returns `None` because `state_peer.state` is `"BotState:awaiting_row"` (string), not `BotState.AWAITING_ROW` (enum member).
**Why it happens:** `vkbottle`'s `BaseStateGroup` serializes state as `"{ClassName}:{value}"`.
**How to avoid:** Always convert: `BotState(state_peer.state.split(":")[-1])` before FSM_CONFIG lookup.
**Warning signs:** `config` is `None`, `AttributeError` on `config.back_state`.

### Pitfall 2: AWAITING_ROW back_state sends to MAIN_MENU without show_main_menu
**What goes wrong:** `/cancel` in `AWAITING_ROW` (from_main_menu=True) calls `storage.set(user_id, BotState.MAIN_MENU, **payload)` but only sends a plain text message. The user is in MAIN_MENU state but no main menu keyboard appears.
**Why it happens:** `MAIN_MENU` state requires displaying a keyboard + reservation seats list. It's not a "send a prompt string" back-state — it requires calling `show_main_menu()`.
**How to avoid:** Detect when `back == BotState.MAIN_MENU` and call `show_main_menu()` instead of a plain `message.answer()`. All needed context keys are in payload: `reservation_id`, `buyer_vk_user_id`, `buyer_vk_api_id`, `buyer_display_name`.

### Pitfall 3: Sending duplicate "back" messages
**What goes wrong:** `cancel_handler` sends a message AND then the handler for the back state also sends a message, resulting in two messages.
**Why it happens:** If `cancel_handler` calls `show_main_menu()`, it transitions the FSM to MAIN_MENU AND sends the menu. No additional message from state handler fires because vkbottle only dispatches to the handler for the NEXT user message, not the current one.
**How to avoid:** This is NOT actually a problem. `cancel_handler` handles the current `/cancel` message. The back state's handler only fires on the user's NEXT message. Each sends exactly one message.

### Pitfall 4: Early row validation uses layout seat count, not db seat count
**What goes wrong:** `get_available_seats_in_row` checks layout max seats but the DB might have a different picture (e.g., if layout.json changed). For `deleting_row_handler`, checking layout availability is wrong — need to check reservation membership.
**Why it happens:** Confusing "row has seats in layout" (always true if row is valid) with "row has seats relevant to this operation."
**How to avoid:** Use operation-specific queries (see Pattern 3 table above). For deletion, query `get_reservation_seats_in_row(reservation_id, row)`. For adding seats, query `get_available_seats_in_row(row)`.

### Pitfall 5: CONTEXT_SWITCH_CONFIRM /cancel behavior
**What goes wrong:** `cancel_handler` sees `back_state=None` for `CONTEXT_SWITCH_CONFIRM` and does `storage.delete()`, abandoning the original work context.
**Why it happens:** Generic `back_state=None` → clear logic doesn't account for the original state stored in payload.
**How to avoid:** Check for `CONTEXT_SWITCH_CONFIRM` specifically. When in this state, `/cancel` should behave like "Нет": restore `original_state`/`original_context` from payload. Mirror the existing `elif text == Btn.NO` branch in `context_switch_handler`.

## Code Examples

### State lookup from Redis string (existing pattern)
```python
# Source: bot/handlers/menu.py, context_switch_handler, line 307
restored_state = BotState(original_state.split(":")[-1])
await storage.set(message.from_id, restored_state, **original_context)
```

### Payload preservation during set (existing pattern)
```python
# Source: bot/handlers/reservation.py, seat_addition_menu_handler, line 425
await storage.set(message.from_id, BotState.AWAITING_ROW, **context)
# context already contains reservation_id, buyer_vk_user_id, etc.
```

### get_context usage (existing pattern)
```python
# Source: bot/handlers/reservation.py, awaiting_row_handler, line 313
context = await storage.get_context(message.from_id)
context['current_row'] = row
await storage.set(message.from_id, BotState.AWAITING_SEATS, **context)
```

### cancel_handler current state read (new pattern)
```python
# New for Phase 12
state_peer = await storage.get(message.from_id)
if state_peer is None:
    # User is IDLE — /cancel does nothing meaningful
    await message.answer(texts.MSG_CANCEL_ALREADY_IDLE, keyboard=commands_keyboard())
    return
current_state_str = state_peer.state  # "BotState:awaiting_seats"
current_state = BotState(current_state_str.split(":")[-1])  # BotState.AWAITING_SEATS
config = FSM_CONFIG[current_state]
back = config.back_state  # BotState.AWAITING_ROW or None
```

### show_main_menu call from cancel_handler (new pattern)
```python
# New for Phase 12 — when back_state is MAIN_MENU
from bot.handlers.menu import show_main_menu  # local import
payload = state_peer.payload
await show_main_menu(
    message, storage,
    reservation_id=payload["reservation_id"],
    vk_user_id=payload["buyer_vk_user_id"],
    buyer_display_name=payload["buyer_display_name"],
    buyer_vk_api_id=payload["buyer_vk_api_id"],
)
```

### Early validation in row handler (new pattern)
```python
# New for Phase 12 — awaiting_row_handler
result = handle_row_input(message.text)
if not result.ok:
    await message.answer(result.error_text)
    return
row = result.row

available = db.get_available_seats_in_row(row)
if not available:
    seat_count = get_seat_count(row)
    await message.answer(texts.ERR_ROW_NO_AVAILABLE_SEATS.format(row=row, seat_count=seat_count))
    return  # stay in AWAITING_ROW
```

## New Text Constants Needed

Add to `bot/texts.py`:

```python
# /cancel back-navigation
MSG_CANCEL_ALREADY_IDLE = "Вы уже в начальном состоянии."

# Early row validation (NAV-03)
ERR_ROW_NO_AVAILABLE_SEATS = "Ряд {row}: нет свободных мест. Введите другой ряд:"
ERR_ROW_NO_BOOKED_SEATS = "Ряд {row}: в этой брони нет мест для удаления. Введите другой ряд:"
ERR_ROW_NO_RESERVED_SEATS = "Ряд {row}: нет зарезервированных мест. Введите другой ряд:"
```

The existing `MSG_CANCEL_FULL` text remains as the fallback for back_state=None cases (IDLE cleared, CONTEXT_SWITCH_CONFIRM cleared). Review: the existing wording "Операция отменена. Состояние сброшено." is accurate for full reset cases. For step-back cases, no cancellation message is needed — just show the restored state's prompt.

## State of the Art

| Old Approach | Current Approach (Phase 12) | Impact |
|---|---|---|
| /cancel → storage.delete() (Phase 10) | /cancel → FSM_CONFIG back_state navigation | Billeters can fix mistakes without restarting |
| No /exit command (pre-Phase 10) | /exit exists, hard resets to IDLE | Already done in Phase 10 |
| Row accepted even if all seats taken | Early validation returns immediately with helpful message | Eliminates wasted seat-entry round trip |

## Implementation Plan Alignment

**12-01 tasks:**
1. Define complete BACK_MAP — done above (already in FSM_CONFIG, AWAITING_ROW ambiguity resolved via `from_main_menu`).
2. Change `cancel_handler` to read `back_state` and navigate; handle AWAITING_ROW ambiguity and CONTEXT_SWITCH_CONFIRM special case.
3. Add `_send_back_state_prompt()` helper or inline navigation logic in `cancel_handler`.
4. Add text constants.

**12-02 tasks:**
1. Verify `/exit` behavior is already correct (it is).
2. Add `get_available_seats_in_row()`, `get_reservation_seats_in_row()`, `get_reserved_seats_in_row()` to `db.py`.
3. Add validation calls to `awaiting_row_handler`, `deleting_row_handler`, `reserve_adding_row_handler`, `reserve_removing_row_handler`.
4. Add error text constants for NAV-03.

## Open Questions

1. **Back-state prompt for RESERVE_ACTION**
   - What we know: `reserve_action_handler` shows reserves list + `reserve_action_keyboard()`. The reserves list is fetched from DB with `db.get_active_reserves()`.
   - What's unclear: Should `/cancel` in `RESERVE_ADDING_ROW` or `RESERVE_REMOVING_ROW` re-fetch and re-display the reserves list, or just say "Возврат к меню резервов" + show keyboard?
   - Recommendation: Re-fetch `get_active_reserves()` and show full `MSG_RESERVE_ACTION_HEADER`. Consistent with how `reserve_command_handler` and `reserve_comment_handler` both call the same display.

2. **cancel_handler signature change**
   - What we know: `cancel_handler(message, storage)` signature is already correct for this use.
   - What's unclear: The `_wrap()` in Router injects storage already. No signature change needed.
   - Recommendation: No changes to router or handler signature.

3. **Early validation for AWAITING_ROW: partial availability**
   - What we know: "no available seats" = all seats in the row are occupied.
   - What's unclear: Should the error message show which seats ARE taken, or just say "no seats available"?
   - Recommendation: Simple message "Ряд {row}: нет свободных мест. Введите другой ряд:" — no need to enumerate taken seats, that's not actionable for the seller.

## Sources

### Primary (HIGH confidence)
- `bot/fsm/config.py` — FSM_CONFIG with all 18 states, back_state fields, forward_states
- `bot/fsm/states.py` — BotState enum, all 18 members
- `bot/fsm/storage.py` — RedisStorage, get/set/delete/get_context methods
- `bot/handlers/commands.py` — cancel_handler and exit_handler implementations
- `bot/handlers/reservation.py` — AWAITING_ROW, AWAITING_SEATS, SEAT_ADDITION_MENU handlers; from_main_menu flag
- `bot/handlers/menu.py` — show_main_menu, main_menu_handler; from_main_menu transitions
- `bot/handlers/deletion.py` — deleting_row_handler, deleting_seats_handler
- `bot/handlers/reserve.py` — reserve_adding_row_handler, reserve_removing_row_handler
- `bot/router.py` — registration order, _wrap, _with_auth_guard
- `bot/utils/db.py` — all existing query functions; confirms no row-level helpers exist
- `bot/utils/layout.py` — get_seat_count, is_valid_row for row validation

### Secondary (MEDIUM confidence)
- Runtime verification: `python3 -c "from bot.fsm.config import FSM_CONFIG; ..."` confirmed all 18 states present and back_state values as documented above.

## Metadata

**Confidence breakdown:**
- BACK_MAP completeness: HIGH — read directly from config.py + verified live
- AWAITING_ROW ambiguity resolution: HIGH — from_main_menu flag confirmed in multiple handlers
- cancel_handler implementation pattern: HIGH — existing patterns (context_switch_handler) show exact same lookup pattern
- NAV-03 early validation: HIGH — db.py functions do not exist yet, query pattern is straightforward SQLAlchemy
- New text constants: HIGH — derived from existing patterns in texts.py

**Research date:** 2026-02-19
**Valid until:** 2026-03-21 (stable codebase)

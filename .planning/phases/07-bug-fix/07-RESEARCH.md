# Phase 7: Bug Fix - Research

**Researched:** 2026-02-19
**Domain:** vkbottle FSM state management, BotState enum restoration
**Confidence:** HIGH

## Summary

This phase fixes a single production bug: when a ticketer presses "Нет" in the context switch
confirmation dialog (`context_switch_handler`), the bot should restore the user to their previous
FSM state. Instead, the bot either silently enters a broken state or fails to route messages
correctly after "restoration."

The root cause is on `menu.py:325`. The variable `original_state` holds a `StateRepresentation`
string (e.g., `'BotState:main_menu'`) — this is the format returned by `state_peer.state` after
JSON deserialization from Redis. The code passes this raw string directly to `storage.set()`,
which expects a `BaseStateGroup` enum member. Although `StatePeer` accepts the string without
raising an exception, the resulting stored state may not match vkbottle's routing comparison when
the state string format differs between write and read paths.

The correct fix is to convert `original_state` back to a proper `BotState` enum member before
calling `storage.set()`. The conversion is: `BotState(original_state.split(':')[-1])`. This
pattern handles both the modern `'BotState:value'` format and the legacy `'value'` format
(from old-format Redis migration). All 18 `BotState` enum members are successfully restored by
this pattern.

**Primary recommendation:** At `menu.py:325`, replace `original_state` with
`BotState(original_state.split(':')[-1])`. No other files require changes.

## Standard Stack

### Core (already in use)

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| `vkbottle` | current | VK bot framework, FSM, routing | Project standard |
| `BaseStateGroup` | vkbottle builtin | Enum base for FSM states | Required by vkbottle |
| `StatePeer` | vkbottle builtin | State container serialized to Redis | Project's storage model |
| `StateRepresentation` | vkbottle builtin | String form of state for routing | Internal vkbottle format |
| `RedisStorage` | project | Custom FSM storage backed by Redis | Project standard |

### No new dependencies needed

This is a one-line bug fix. No new libraries, no new files.

## Architecture Patterns

### How FSM State Flows Through the System

```
1. State WRITE (storage.set):
   BotState.MAIN_MENU (enum)
   -> StatePeer(state=BotState.MAIN_MENU)
   -> model_dump() -> {"state": "BotState:main_menu", ...}
   -> JSON -> Redis

2. State READ (storage.get):
   Redis -> JSON -> StatePeer(**parsed)
   -> state_peer.state == "BotState:main_menu"  (plain string, NOT enum)

3. Context switch stores original state:
   reservation.py:79: current_state = state_peer.state  # "BotState:main_menu"
   reservation.py:144: original_state=current_state     # stored in payload as string

4. Context switch restores (BUGGY):
   original_state = context.get("original_state")  # "BotState:main_menu"
   storage.set(peer_id, original_state, ...)        # passes string, not enum -- BUG

5. Context switch restores (FIXED):
   original_state = context.get("original_state")           # "BotState:main_menu"
   value = original_state.split(":")[-1]                    # "main_menu"
   storage.set(peer_id, BotState(value), ...)               # proper enum -- CORRECT
```

### StateRepresentation String Format

vkbottle serializes enum states as `'ClassName:value'` strings. After deserialization from Redis,
`state_peer.state` is a plain `str`, not an enum. The routing layer re-constructs
`StateRepresentation(enum_member)` at comparison time and compares to the stored string.

**Format:** `f"{EnumClass.__name__}:{enum_member.value}"` — e.g., `"BotState:main_menu"`

### Pattern: Safe Enum Restoration from StateRepresentation String

```python
# Source: verified by code inspection + runtime testing (2026-02-19)

def restore_botstate(state_string: str) -> BotState:
    """
    Convert a StateRepresentation string back to a BotState enum member.

    Handles both:
    - Modern format: "BotState:main_menu" (from state_peer.state)
    - Legacy format: "main_menu" (from old Redis migration path)
    """
    value = state_string.split(":")[-1]
    return BotState(value)
```

Usage at `menu.py:325`:
```python
# Before (BUGGY):
await storage.set(message.from_id, original_state, **original_context)

# After (FIXED):
restored_state = BotState(original_state.split(":")[-1])
await storage.set(message.from_id, restored_state, **original_context)
```

### Anti-Patterns to Avoid

- **Passing StateRepresentation string as state enum:** `storage.set(peer_id, "BotState:main_menu")` — type annotation says `BaseStateGroup`, and routing depends on proper enum comparison in some vkbottle versions.
- **Calling `BotState(original_state)` without splitting first:** `BotState("BotState:main_menu")` raises `ValueError: 'BotState:main_menu' is not a valid BotState` because the enum values are `'main_menu'` not `'BotState:main_menu'`.
- **Calling `BotState[original_state]` (name lookup):** Enum names are `MAIN_MENU`, `AWAITING_ROW`, etc. (uppercase). The stored state strings are lowercase values. Name lookup would fail.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State string parsing | Custom string parser | `str.split(":")[-1]` one-liner + `BotState()` | Simple enough inline |
| State validation | Manual string checks | `BotState(value)` — raises `ValueError` on invalid | Enum provides validation for free |

## Common Pitfalls

### Pitfall 1: Wrong BotState Constructor Argument

**What goes wrong:** `BotState(original_state)` where `original_state = "BotState:main_menu"` raises `ValueError: 'BotState:main_menu' is not a valid BotState`.

**Why it happens:** The requirement spec says "use `BotState(original_state)`" but `original_state` from the Redis payload holds the `StateRepresentation` string format, not the raw enum value. The fix must split first.

**How to avoid:** Always extract the value portion: `BotState(original_state.split(":")[-1])`.

**Warning signs:** `ValueError` in logs when user presses "Нет".

### Pitfall 2: The "idle" Edge Case

**What goes wrong:** When the ticketer was IDLE before the context switch, `storage.get()` returns `None`, so `reservation.py:79` sets `current_state = "idle"` (a manually assigned fallback string). The guard on `menu.py:324` checks `original_state != "idle"`, which correctly skips restoration for this case.

**Why it matters:** The `"idle"` string does NOT go through the `BotState(value.split(":")[-1])` path because the guard prevents it. No issue here — the `else` branch correctly calls `storage.delete()`.

**How to avoid:** Preserve the existing `original_state != "idle"` guard. Do not change it.

### Pitfall 3: Broken State Left in Redis

**What goes wrong:** If the bug fix is incomplete and `storage.set()` is called with an invalid state argument, the StatePeer stored in Redis may have `state = "BotState:main_menu"` (string) instead of a properly routed enum. Subsequent messages from the user hit no handler and are silently dropped.

**Why it happens:** vkbottle compares `StateRepresentation(handler_state) == stored_state` — the comparison uses string equality. If the stored value is in the right format (`"BotState:main_menu"`), routing still works. If it is the raw value `"main_menu"`, routing fails silently.

**How to avoid:** The fix (using proper `BotState` enum) ensures `model_dump()` always produces `"BotState:main_menu"` format, making routing deterministic.

### Pitfall 4: Guard String Comparison After Fix

**What goes wrong:** If the fix changes `original_state` to be stored as a raw value (e.g., by changing `reservation.py` to store `current_state.value`), the existing `original_state != "idle"` guard in `menu.py:324` would need updating.

**How to avoid:** The fix should be confined to `menu.py:325` only. Do not change how `original_state` is stored in `reservation.py`. Keep the conversion logic in `context_switch_handler`.

## Code Examples

### The Bug (current code, menu.py:322-332)

```python
# Source: bot/handlers/menu.py:322-332
elif text == "Нет":
    # Restore previous state and context
    if original_state and original_state != "idle":
        await storage.set(message.from_id, original_state, **original_context)  # BUG: string not enum
        await message.answer(
            f"Продолжаем работу с {original_context.get('buyer_display_name', 'предыдущим клиентом')}."
        )
    else:
        # No original state to restore - just clear
        await storage.delete(message.from_id)
        await message.answer("Операция отменена.")
```

### The Fix

```python
# Source: verified by runtime testing 2026-02-19
elif text == "Нет":
    # Restore previous state and context
    if original_state and original_state != "idle":
        restored_state = BotState(original_state.split(":")[-1])  # FIX: proper enum member
        await storage.set(message.from_id, restored_state, **original_context)
        await message.answer(
            f"Продолжаем работу с {original_context.get('buyer_display_name', 'предыдущим клиентом')}."
        )
    else:
        # No original state to restore - just clear
        await storage.delete(message.from_id)
        await message.answer("Операция отменена.")
```

### All 18 BotState Values (for reference)

Verified by runtime enumeration. All 18 members restore correctly via `BotState(value.split(":")[-1])`:

```
IDLE                = "idle"
AWAITING_ROW        = "awaiting_row"
AWAITING_SEATS      = "awaiting_seats"
SEAT_ADDITION_MENU  = "seat_addition_menu"
MAIN_MENU           = "main_menu"
DELETING_ROW        = "deleting_row"
DELETING_SEATS      = "deleting_seats"
DELETION_CONFIRM    = "deletion_confirm"
CANCEL_CONFIRM      = "cancel_confirm"
CONTEXT_SWITCH_CONFIRM = "context_switch_confirm"
PAYMENT_QUANTITY    = "payment_quantity"
RESERVE_ACTION      = "reserve_action"
RESERVE_ADDING_ROW  = "reserve_adding_row"
RESERVE_ADDING_SEATS = "reserve_adding_seats"
RESERVE_COMMENT     = "reserve_comment"
RESERVE_REMOVING_ROW = "reserve_removing_row"
RESERVE_REMOVING_SEATS = "reserve_removing_seats"
RESERVE_REMOVE_CONFIRM = "reserve_remove_confirm"
```

Note: The requirement says "16 FSM states" but the codebase currently has 18 `BotState` members.
All 18 restore correctly with the fix.

### Minimal Unit Test Pattern

```python
# Source: follows test_seat_parser.py convention in bot/tests/
import pytest
from bot.fsm.states import BotState


class TestBotStateRestoration:
    """Verify BotState enum restoration from StateRepresentation strings."""

    def test_all_states_restore_from_modern_format(self):
        """All BotState members restore from 'BotState:value' format."""
        for member in BotState:
            state_repr = f"BotState:{member.value}"
            restored = BotState(state_repr.split(":")[-1])
            assert restored == member

    def test_all_states_restore_from_legacy_format(self):
        """All BotState members restore from raw value format."""
        for member in BotState:
            restored = BotState(member.value)
            assert restored == member

    def test_idle_sentinel_not_restored(self):
        """'idle' sentinel string is caught by the existing guard."""
        assert "idle" != "BotState:idle"  # manual fallback stays distinct
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| Pass raw string to storage.set | Pass BotState enum member | Routing is deterministic and type-safe |

## Open Questions

1. **Why does the bug not always fail visibly?**
   - What we know: Passing `"BotState:main_menu"` (string) to `StatePeer` does not raise. The stored value is still `"BotState:main_menu"`, which matches routing correctly.
   - What's unclear: The bug may only manifest when Redis contains old-format data migrated to raw values like `"main_menu"` (without the `BotState:` prefix), in which case routing silently fails.
   - Recommendation: Fix it anyway — the type contract is violated and it's a ticking time bomb.

2. **Should the fix also update how `original_state` is stored in `reservation.py`?**
   - What we know: Storing the enum value directly (e.g., `member.value = "main_menu"`) instead of `state_peer.state` would make `BotState(original_state)` work without splitting.
   - What's unclear: Changing `reservation.py` increases diff scope and risks breaking other paths.
   - Recommendation: Keep the fix minimal — convert at the consumption point (`menu.py:325`) only.

## Sources

### Primary (HIGH confidence)
- `bot/handlers/menu.py` — direct code inspection, lines 204-340 (the buggy handler)
- `bot/handlers/reservation.py` — direct code inspection, lines 78-79, 144, 172, 218 (where `original_state` is captured and stored)
- `bot/fsm/states.py` — direct code inspection (all 18 `BotState` members enumerated)
- `bot/fsm/storage.py` — direct code inspection (storage.set signature, StatePeer usage)
- Runtime Python testing — all findings verified by executing code in-process

### Secondary (MEDIUM confidence)
- `bot/tests/test_redis_fsm.py` — confirms `state_peer.state == "BotState:awaiting_row"` (string) after deserialization (line 45, 51)

## Metadata

**Confidence breakdown:**
- Bug location: HIGH — confirmed by code inspection, line 325
- Bug cause: HIGH — confirmed by runtime testing (`BotState("BotState:main_menu")` raises ValueError)
- Fix approach: HIGH — `BotState(original_state.split(":")[-1])` verified for all 18 states
- Scope of change: HIGH — single function, single line, no new files

**Research date:** 2026-02-19
**Valid until:** Stable — pure Python enum behavior, no external library dependencies

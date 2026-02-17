# Phase 4: Управление резервами (админ) - Research

**Researched:** 2026-02-18
**Domain:** VKBottle FSM, SQLAlchemy ORM, admin auth, reserve CRUD
**Confidence:** HIGH — all findings based on direct codebase inspection

---

## Summary

Phase 4 adds admin-only `/reserve` command with two sub-flows: adding a reserve (FSM: row -> seats -> comment) and removing a reserve (FSM: row -> seats -> confirm). Reserves are `SeatAssignment` rows with `status=RESERVED`, `reservation_id=NULL`, and a mandatory `note`.

The codebase already has all necessary infrastructure: `AppUser.role` (`UserRole.ADMIN` / `UserRole.SELLER`), `db.is_user_admin()`, `SeatStatus.RESERVED`, `SeatAssignment.note`, `AuditLog`, `parse_seats()`, `is_valid_row()`, `is_valid_seat()`, and the seat-occupied error message that already renders reserve info. No schema changes are needed. The only new artifacts are: new FSM states in `BotState`, a new handler file `bot/handlers/reserve.py`, new db functions, an optional keyboard, and registration in `bot/main.py`.

**Primary recommendation:** Follow the exact structural pattern of `bot/handlers/deletion.py` — it is the closest analog: typed-row -> typed-seats -> confirm, same storage pattern, same error handling, same `from bot.handlers.menu import show_main_menu` local import discipline.

---

## Standard Stack

The project's stack is fixed. Phase 4 uses no new libraries.

### Core (already installed)
| Component | Version | Purpose |
|-----------|---------|---------|
| VKBottle | installed | Bot API, message routing, FSM states |
| SQLAlchemy | installed | ORM, session management |
| Redis (asyncio) | installed | FSM state persistence |
| Python 3.14 | installed | Runtime |

### Reused Utilities
| Utility | Location | Purpose |
|---------|----------|---------|
| `parse_seats` | `bot/utils/seat_parser.py` | Seat number parsing (spaces/commas/ranges) |
| `is_valid_row` | `bot/utils/layout.py` | Row validation against layout.json |
| `is_valid_seat` | `bot/utils/layout.py` | Seat validation against layout.json |
| `get_seat_count` | `bot/utils/layout.py` | Max seats for a row |
| `get_row_range` | `bot/utils/layout.py` | Min/max row numbers |
| `db.is_user_admin` | `bot/utils/db.py` | Check `AppUser.role == ADMIN` by VK ID |
| `RedisStorage` | `bot/fsm/storage.py` | `set()`, `get_context()`, `delete()` |
| `AuditLog` model | `models/audit.py` | Reserve added/removed events |
| `SeatAssignment` model | `models/seat_assignment.py` | All seat state |

**No new libraries needed. No schema changes needed.**

---

## Architecture Patterns

### How Command Handlers Work (verified in commands.py)

```python
# Source: bot/handlers/commands.py
bot.on.message(text="/start")(start_handler)
bot.on.message(text="/cancel")(cancel_with_storage)
```

The `/reserve` command handler registers with `bot.on.message(text="/reserve")`.

### How State-Gated Handlers Work (verified in deletion.py)

```python
# Source: bot/handlers/deletion.py
bot.on.message(state=BotState.DELETING_ROW)(deleting_row_with_storage)
```

Each FSM state has exactly one handler. State transitions are explicit `storage.set(peer_id, BotState.X, **context)` calls.

### Handler Registration Pattern (verified in all handlers)

```python
# Source: bot/handlers/deletion.py (pattern used in every handler file)
def register_handlers(bot: Bot):
    storage = bot.state_dispenser

    async def handler_with_storage(message: Message):
        await actual_handler(message, storage)

    bot.on.message(state=BotState.STATE_NAME)(handler_with_storage)
```

The `/reserve` command handler needs this same wrapper approach.

### FSM State Pattern (verified in bot/fsm/states.py)

```python
# Source: bot/fsm/states.py
class BotState(BaseStateGroup):
    IDLE = "idle"
    AWAITING_ROW = "awaiting_row"
    # etc.
```

New states for Phase 4 — add to `BotState`:
```python
# Reserve flow (Phase 4)
RESERVE_ACTION = "reserve_action"            # Choose: add or remove
RESERVE_ADDING_ROW = "reserve_adding_row"   # Input row for new reserve
RESERVE_ADDING_SEATS = "reserve_adding_seats" # Input seats for new reserve
RESERVE_COMMENT = "reserve_comment"          # Input mandatory comment
RESERVE_REMOVING_ROW = "reserve_removing_row" # Input row to remove reserve
RESERVE_REMOVING_SEATS = "reserve_removing_seats" # Input seats to remove
RESERVE_REMOVE_CONFIRM = "reserve_remove_confirm" # Confirm removal
```

### Admin Check Pattern (verified in deletion.py + db.py)

```python
# Source: bot/handlers/deletion.py + bot/utils/db.py
# In cancel_confirm_handler:
is_admin = db.is_user_admin(message.from_id)

# In db.py, is_user_admin:
def is_user_admin(vk_user_id: int) -> bool:
    with SessionLocal() as session:
        stmt = (
            select(AppUser)
            .where(AppUser.vk_user_id == vk_user_id)
            .where(AppUser.is_active == True)
        )
        user = session.execute(stmt).scalar_one_or_none()
        return user is not None and user.role == UserRole.ADMIN
```

The `/reserve` command handler calls `db.is_user_admin(message.from_id)` at the top and returns if not admin.

### Context Storage Pattern (verified across all handlers)

```python
# Source: bot/handlers/reservation.py
context = await storage.get_context(message.from_id)
context['current_row'] = row
await storage.set(message.from_id, BotState.NEXT_STATE, **context)
```

Keys used in reserve flow: `current_row`, `seats_to_reserve`, `reserve_comment`, `seats_to_remove`.

### SeatAssignment Creation for Reserves (derived from models + existing db.py)

```python
# Pattern: like add_seats_to_reservation but status=RESERVED, reservation_id=None
assignment = SeatAssignment(
    row_number=row,
    seat_number=seat,
    status=SeatStatus.RESERVED,
    reservation_id=None,   # Critical: NULL for reserves
    created_by_user_id=user_id,
    note=comment,          # Mandatory comment stored here
)
```

### Reserve Removal Pattern (derived from release_seats)

```python
# Pattern: like release_seats but status=RESERVED instead of BOOKED
stmt = (
    select(SeatAssignment)
    .where(SeatAssignment.row_number == row)
    .where(SeatAssignment.seat_number.in_(seats))
    .where(SeatAssignment.released_at.is_(None))
    .where(SeatAssignment.status == SeatStatus.RESERVED)
    # No reservation_id filter - reserves have reservation_id=NULL
)
```

### Audit Log Pattern (verified in db.py)

```python
# Source: bot/utils/db.py - create_reservation, add_seats_to_reservation
audit = AuditLog(
    actor_type=ActorType.USER,
    actor_user_id=user_id,
    action_type="reserve_added",      # or "reserve_removed"
    entity_type="seat_assignment",
    entity_id=str(assignment.id),     # first assignment id, or comma-joined
    payload={
        "row": row,
        "seats": seats,
        "comment": comment,           # for reserve_added
        "previous_note": note,        # for reserve_removed (audit requirement)
    }
)
```

### Local Import Pattern for Circular Dependencies (verified)

```python
# Source: bot/handlers/payment.py, bot/handlers/menu.py
# At point of use, not at module top:
from bot.handlers.menu import show_main_menu
```

The reserve handler will not need `show_main_menu` but should use local imports if it calls payment or menu handlers.

### Existing "Seats Already Occupied" Error Display (verified in reservation.py)

The check in `awaiting_seats_handler` already renders reserves correctly:
```python
# Source: bot/handlers/reservation.py
if assignment.status == SeatStatus.RESERVED:
    status_text = "Резерв"
    detail = assignment.note or "без комментария"
```

The requirement "display reserves during occupancy check" is **already implemented**. Phase 4 needs to verify this works with the reserve comment, not re-implement it.

### Recommended Project Structure for Phase 4

```
bot/
├── handlers/
│   ├── reserve.py          # NEW: all /reserve command handlers
│   └── (existing files unchanged)
├── fsm/
│   └── states.py           # MODIFIED: add 7 new BotState values
├── utils/
│   └── db.py               # MODIFIED: add add_reserve(), release_reserve() functions
├── keyboards.py             # MODIFIED: add reserve_action_keyboard()
└── main.py                  # MODIFIED: import and register reserve handlers
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Seat parsing | Custom parser | `parse_seats()` | Already handles all formats, tested |
| Row validation | Custom validator | `is_valid_row()` | Already loads layout.json |
| Seat validation | Custom validator | `is_valid_seat()` | Already validates against row capacity |
| Admin check | Custom role check | `db.is_user_admin()` | Already queries AppUser.role |
| Seat occupancy query | Custom query | Pattern from `get_seat_assignment()` | Handles `released_at IS NULL` correctly |
| Partial index awareness | Manual | Use `released_at IS NULL` filter | DB has partial unique index on it |
| Session management | Manual session | `with SessionLocal() as session` | Already handles commit/rollback |
| Context persistence | Manual Redis | `storage.set(peer_id, state, **context)` | Already handles StatePeer serialization |

**Key insight:** The reserve flow is structurally identical to the deletion flow. `bot/handlers/deletion.py` is the template to copy and adapt, not start from scratch.

---

## Common Pitfalls

### Pitfall 1: State String Comparison (CRITICAL — confirmed bug in Phase 3)
**What goes wrong:** Using `BotState.MAIN_MENU.value` or `BotState.MAIN_MENU` directly for string comparison. VKBottle stores state as `"BotState:reserve_action"` not `"reserve_action"`.
**Why it happens:** VKBottle `BaseStateGroup` prefixes state name with class name when serializing.
**How to avoid:** Only compare states via `storage.get()` and `state_peer.state` comparisons using `str(BotState.X)`. The existing `awaiting_seats_handler` uses state routing via `bot.on.message(state=BotState.X)` which VKBottle handles internally — this is correct and does not need string comparison.
**Warning signs:** Handlers that check `current_state == str(BotState.X)` vs `current_state == BotState.X.value` — use `str(BotState.X)`.

### Pitfall 2: `reservation_id=NULL` vs `reservation_id=0`
**What goes wrong:** Storing `reservation_id=0` or some sentinel instead of `NULL`. The partial unique index `seat_assignments_one_active_per_seat` does not care about `reservation_id` — it only checks `(row_number, seat_number)` with `released_at IS NULL`. A reserve occupies the seat fully.
**How to avoid:** Set `reservation_id=None` in Python (SQLAlchemy maps to SQL NULL).

### Pitfall 3: Forgetting `released_at IS NULL` Filter for RESERVED Seats
**What goes wrong:** Querying `status=RESERVED` without `released_at IS NULL` returns both active and historical reserves.
**How to avoid:** Always add `.where(SeatAssignment.released_at.is_(None))` when checking active reserves.

### Pitfall 4: Comment State Transition — Storing Comment Before FSM Transition
**What goes wrong:** Trying to get `reserve_comment` from context in the wrong state. The comment is entered in `RESERVE_COMMENT` state and must be carried forward via `storage.set(... comment=text)`.
**How to avoid:** In `reserve_comment_handler`, read `text = message.text.strip()`, validate non-empty, then call `db.add_reserve(row, seats, comment, user_id)` and reset FSM.

### Pitfall 5: Handler Registration Order
**What goes wrong:** `/reserve` command may match before state-specific handlers if registered last; or state handlers for new states get priority over `/reserve` if registered in wrong order.
**How to avoid:** Register `/reserve` text handler first (in `commands.py` or `reserve.py`), then state handlers. Follow existing pattern in `main.py` — command handlers first, then state handlers via their own `register_handlers()`.

### Pitfall 6: `get_default_seller_id()` for Admin Operations
**What goes wrong:** Using `get_default_seller_id()` for the `created_by_user_id` field — this returns the first active user, not the actual admin performing the action.
**How to avoid:** Look up the `AppUser` by `message.from_id` (VK user ID) to get their `AppUser.id`. Add a helper `db.get_app_user_by_vk_id(vk_id: int) -> Optional[AppUser]` or reuse the lookup inside `is_user_admin`.

### Pitfall 7: Validation of Seats for Reserve Removal — Must Check `status=RESERVED`
**What goes wrong:** Trying to release a seat that is `BOOKED` or `PAID` (not a reserve). The validation query must filter `status=RESERVED`.
**How to avoid:** In the DB function, query specifically for `status=SeatStatus.RESERVED`. Return a clear error list to the handler if any requested seat is not an active reserve.

---

## Code Examples

### /reserve Command Handler Entry Point
```python
# Source: pattern from bot/handlers/commands.py
async def reserve_command_handler(message: Message, storage: RedisStorage):
    """Handle /reserve command — admin only."""
    if not db.is_user_admin(message.from_id):
        await message.answer("Управление резервами доступно только администраторам.")
        return

    await message.answer(
        "Управление резервами. Выберите действие:",
        keyboard=reserve_action_keyboard()
    )
    await storage.set(message.from_id, BotState.RESERVE_ACTION)
```

### Reserve Action Keyboard
```python
# Source: pattern from bot/keyboards.py
def reserve_action_keyboard() -> str:
    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Text("Добавить резерв"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("Удалить резерв"), color=KeyboardButtonColor.NEGATIVE)
    keyboard.row()
    keyboard.add(Text("Отмена"), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()
```

### DB Function: add_reserve
```python
# Source: derived from add_seats_to_reservation in bot/utils/db.py
def add_reserve(
    row: int,
    seats: List[int],
    comment: str,
    user_id: int,
) -> List[SeatAssignment]:
    with SessionLocal() as session:
        try:
            # Check all seats are available first (same as add_seats_to_reservation)
            for seat in seats:
                stmt = (
                    select(SeatAssignment)
                    .where(SeatAssignment.row_number == row)
                    .where(SeatAssignment.seat_number == seat)
                    .where(SeatAssignment.released_at.is_(None))
                )
                existing = session.execute(stmt).scalar_one_or_none()
                if existing:
                    raise SeatOccupiedError(row, seat, existing)

            # Create reserve assignments
            assignments = []
            for seat in seats:
                assignment = SeatAssignment(
                    row_number=row,
                    seat_number=seat,
                    status=SeatStatus.RESERVED,
                    reservation_id=None,
                    created_by_user_id=user_id,
                    note=comment,
                )
                session.add(assignment)
                assignments.append(assignment)

            session.commit()
            for a in assignments:
                session.refresh(a)

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="reserve_added",
                entity_type="seat_assignment",
                entity_id=str(assignments[0].id),
                payload={"row": row, "seats": seats, "comment": comment},
            )
            session.add(audit)
            session.commit()

            return assignments

        except SeatOccupiedError:
            session.rollback()
            raise
        except IntegrityError as e:
            session.rollback()
            raise DatabaseError(f"Integrity error: {e}")
        except Exception as e:
            session.rollback()
            raise DatabaseError(f"Failed to add reserve: {e}")
```

### DB Function: release_reserve
```python
# Source: derived from release_seats in bot/utils/db.py
def release_reserve(
    row: int,
    seats: List[int],
    user_id: int,
) -> tuple[int, List[str]]:
    """Returns (released_count, list_of_notes_for_audit)."""
    with SessionLocal() as session:
        try:
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.row_number == row)
                .where(SeatAssignment.seat_number.in_(seats))
                .where(SeatAssignment.released_at.is_(None))
                .where(SeatAssignment.status == SeatStatus.RESERVED)
            )
            assignments = session.execute(stmt).scalars().all()

            found_seats = {a.seat_number for a in assignments}
            not_reserved = set(seats) - found_seats
            if not_reserved:
                raise DatabaseError(
                    f"Seats not in RESERVED status: {sorted(not_reserved)}"
                )

            notes = [a.note for a in assignments]
            now = datetime.utcnow()
            for assignment in assignments:
                assignment.released_at = now
                assignment.released_by_user_id = user_id

            session.commit()

            # Audit log
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="reserve_removed",
                entity_type="seat_assignment",
                entity_id=",".join(str(a.id) for a in assignments),
                payload={
                    "row": row,
                    "seats": seats,
                    "previous_notes": notes,
                },
            )
            session.add(audit)
            session.commit()

            return len(assignments), notes

        except DatabaseError:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise DatabaseError(f"Failed to release reserve: {e}")
```

### DB Helper: get_app_user_by_vk_id
```python
# Source: pattern from db.is_user_admin — extract the user lookup
def get_app_user_by_vk_id(vk_user_id: int) -> Optional[AppUser]:
    with SessionLocal() as session:
        stmt = (
            select(AppUser)
            .where(AppUser.vk_user_id == vk_user_id)
            .where(AppUser.is_active == True)
        )
        return session.execute(stmt).scalar_one_or_none()
```

### Handler Registration in main.py
```python
# Source: bot/main.py — add after existing handler imports
from bot.handlers import commands, reservation, menu, deletion, payment, reserve

# In setup():
reserve.register_handlers(bot)
```

---

## State of the Art

| Old Approach | Current Approach | Impact for Phase 4 |
|--------------|------------------|-------------------|
| `AppUser.is_admin` boolean field | `AppUser.role` enum (`ADMIN`/`SELLER`) | Use `UserRole.ADMIN`, not a boolean |
| `BotState.X.value` string comparison | `str(BotState.X)` comparison | Must use `str()` form in any manual comparisons |
| Separate context storage | `StatePeer.payload` via `storage.set(**context)` | Context lives in Redis with state; use `storage.get_context()` |

**No deprecated patterns in scope for Phase 4.**

---

## Open Questions

1. **`get_app_user_id_by_vk_id` for `created_by_user_id`**
   - What we know: `get_default_seller_id()` is a placeholder and is not admin-aware
   - What's unclear: Whether to add a new `db.get_app_user_by_vk_id()` helper or inline the lookup
   - Recommendation: Add `get_app_user_by_vk_id()` to `db.py` — it will be reused and makes the intent explicit

2. **RESERVE_ACTION state keyboard handling: what happens to `/cancel` in RESERVE_ACTION?**
   - What we know: `/cancel` clears FSM regardless of state (commands.py)
   - What's unclear: Whether "Отмена" keyboard button in RESERVE_ACTION should also clear state
   - Recommendation: Yes — "Отмена" in RESERVE_ACTION handler calls `storage.delete()` and sends confirmation, matching `/cancel` semantics

3. **Multi-seat reserve: one note covers all seats in that batch**
   - What we know: `SeatAssignment.note` is per-row in a single `RESERVE_ADDING_SEATS` step
   - What's unclear: Whether different rows can be added in one `/reserve` session (multi-row reserve)
   - Recommendation: Per the requirements (`RESERVE_ADDING_ROW -> RESERVE_ADDING_SEATS -> RESERVE_COMMENT`), one row per session. The comment applies to all seats in that one row. Do not implement multi-row reserve add in Phase 4.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `bot/handlers/deletion.py` — structural template for reserve flow
- Direct code inspection: `bot/utils/db.py` — `is_user_admin`, `add_seats_to_reservation`, `release_seats`, `AuditLog` patterns
- Direct code inspection: `bot/fsm/states.py` — `BotState` definition
- Direct code inspection: `bot/fsm/storage.py` — `RedisStorage.set()`, `get_context()`, `update_context()`
- Direct code inspection: `models/seat_assignment.py` — `SeatStatus.RESERVED`, `note` field, `released_at` field
- Direct code inspection: `models/user.py` + `models/base.py` — `AppUser.role`, `UserRole.ADMIN`
- Direct code inspection: `models/audit.py` — `AuditLog` schema
- Direct code inspection: `bot/handlers/reservation.py` — existing reserve display in occupied-seats error

### Secondary (MEDIUM confidence)
- Phase 3 plan (`03-03-PLAN.md`) — confirmed `str(BotState.X)` vs `.value` pitfall

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries, all from codebase
- Architecture patterns: HIGH — directly read from all existing handler files
- DB patterns: HIGH — directly read from `bot/utils/db.py`
- FSM patterns: HIGH — directly read from `bot/fsm/states.py` and `storage.py`
- Pitfalls: HIGH — confirmed from Phase 3 incident (`str(BotState.X)` bug) and model inspection

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days — stable codebase, no fast-moving external dependencies)

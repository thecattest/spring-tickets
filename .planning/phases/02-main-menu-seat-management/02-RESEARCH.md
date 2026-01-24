# Phase 2: Главное меню и удаление мест - Research

**Researched:** 2026-01-24
**Domain:** VKBottle bot interface patterns, FSM context management, batch database operations
**Confidence:** HIGH

## Summary

Phase 2 builds a menu-driven interface for managing existing reservations. When a seller forwards a message from a client with an active reservation, the bot displays all seats grouped by row with status indicators, and provides action buttons for adding/deleting seats or canceling the reservation.

The standard approach uses VKBottle's inline keyboard builder with multiple rows, leverages existing seat parser and formatting utilities, and implements atomic database operations for seat deletion. Context conflict handling requires checking FSM state before switching clients and prompting for confirmation.

**Primary recommendation:** Extend existing patterns from Phase 1 (seat parser, FSM storage, db operations) with multi-button inline keyboards, range formatting for consecutive seats, and permission-aware validation for deletion operations.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| VKBottle | 4.0.0+ | VK Bot API framework | Asynchronous, built-in FSM, inline keyboard support, message event handling |
| SQLAlchemy | 2.0.0+ | ORM and database operations | Atomic transactions, batch UPDATE with WHERE clauses, session management |
| Redis | 5.0.0+ | FSM state storage | Permanent storage (no TTL), StatePeer serialization already implemented |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| itertools | stdlib | Grouping consecutive numbers | Converting seat lists to ranges (e.g., "5-9" instead of "5, 6, 7, 8, 9") |
| collections.defaultdict | stdlib | Grouping by row | Already used in messages.py for seat organization |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| VKBottle Callback buttons | Text-based buttons | Callback buttons enable event-driven responses but Text buttons are simpler and already working in Phase 1 |
| itertools.groupby | Manual range detection | groupby is more Pythonic but requires careful sorting; manual is more explicit |

**Installation:**
No additional dependencies needed - all libraries already in requirements.txt

## Architecture Patterns

### Recommended Project Structure
```
bot/
├── handlers/
│   ├── reservation.py         # Existing: creation + addition
│   └── menu.py                # NEW: main menu + deletion handlers
├── keyboards.py               # Extend with menu keyboards
├── messages.py                # Extend with seat list formatting
└── utils/
    ├── seat_parser.py         # Reuse for deletion input
    └── formatting.py          # NEW: range formatting utility
```

### Pattern 1: Multi-Button Inline Keyboard
**What:** VKBottle keyboard builder with `row()` to create multiple button rows
**When to use:** Main menu with 4 action buttons, confirmation dialogs

**Example:**
```python
# Source: https://github.com/vkbottle/vkbottle/blob/master/docs/tutorial/keyboards-attachments.md
from vkbottle import Keyboard, KeyboardButtonColor, Text

def main_menu_keyboard() -> str:
    """
    Main menu keyboard with 4 action buttons in 2 rows.

    Layout:
    [Добавить] [Удалить]
    [Удалить все] [Оплата]
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text("Добавить"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("Удалить"), color=KeyboardButtonColor.NEGATIVE)
    keyboard.row()
    keyboard.add(Text("Удалить все"), color=KeyboardButtonColor.NEGATIVE)
    keyboard.add(Text("Оплата"), color=KeyboardButtonColor.POSITIVE)

    return keyboard.get_json()
```

### Pattern 2: Confirmation Dialog with Inline Keyboard
**What:** Two-button keyboard for yes/no confirmation
**When to use:** Before seat deletion, before reservation cancellation

**Example:**
```python
def confirmation_keyboard() -> str:
    """
    Simple confirmation dialog.

    Layout:
    [Подтвердить] [Отмена]
    """
    keyboard = Keyboard(one_time=False, inline=True)

    keyboard.add(Text("Подтвердить"), color=KeyboardButtonColor.POSITIVE)
    keyboard.add(Text("Отмена"), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()
```

### Pattern 3: Consecutive Number Range Formatting
**What:** Convert list of consecutive integers to compact range notation
**When to use:** Displaying seat lists grouped by row with status

**Example:**
```python
# Source: https://jonathanchang.org/blog/group-consecutive-number-ranges/
from itertools import groupby
from operator import itemgetter

def format_seat_ranges(seats: list[int]) -> str:
    """
    Format consecutive seats as ranges.

    Args:
        seats: Sorted list of seat numbers

    Returns:
        Formatted string like "1-3, 5, 7-9"
    """
    if not seats:
        return ""

    ranges = []
    for _, g in groupby(enumerate(seats), lambda t: t[0] - t[1]):
        group = list(map(itemgetter(1), g))
        if len(group) == 1:
            ranges.append(str(group[0]))
        else:
            ranges.append(f"{group[0]}-{group[-1]}")

    return ", ".join(ranges)
```

**Key insight:** The groupby trick uses `enumerate(seats)` to pair each seat with its index. For consecutive seats, the difference `index - seat_number` remains constant, so they group together.

### Pattern 4: Batch Seat Release (Atomic)
**What:** Update multiple SeatAssignment rows with `released_at = NOW()` in single transaction
**When to use:** Deleting selected seats, canceling entire reservation

**Example:**
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html
from sqlalchemy import update, select
from datetime import datetime

def release_seats(
    reservation_id: int,
    row: int,
    seats: list[int],
    user_id: int
) -> int:
    """
    Release (delete) seats from reservation atomically.

    Returns:
        Count of released seats
    """
    with SessionLocal() as session:
        try:
            # Update seats in single statement
            stmt = (
                update(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.row_number == row)
                .where(SeatAssignment.seat_number.in_(seats))
                .where(SeatAssignment.released_at.is_(None))
                .values(released_at=datetime.utcnow())
            )
            result = session.execute(stmt)

            # Update reservation last_activity_at
            reservation = session.get(Reservation, reservation_id)
            reservation.last_activity_at = datetime.utcnow()

            session.commit()

            # Return count of affected rows
            return result.rowcount

        except Exception as e:
            session.rollback()
            raise DatabaseError(f"Failed to release seats: {e}")
```

**Note:** Using `.values(released_at=datetime.utcnow())` sets the timestamp at execution time. The `.rowcount` attribute returns how many rows were actually updated.

### Pattern 5: FSM Context Conflict Detection
**What:** Check if FSM state is not IDLE before accepting new client forward
**When to use:** In forwarded_message_handler before switching clients

**Example:**
```python
async def forwarded_message_handler(message: Message, storage: RedisStorage):
    """Handle forwarded message - create or show existing reservation."""

    # Check current FSM state
    state_peer = await storage.get(message.from_id)
    current_state = state_peer.state if state_peer else "idle"

    if current_state != "idle":
        # Seller is working with another client
        context = state_peer.payload
        current_client = context.get("buyer_display_name", "другого клиента")

        await message.answer(
            f"Сейчас вы работаете с {current_client}.\n"
            f"Завершите операцию или /cancel для отмены.",
            keyboard=get_empty_keyboard()
        )
        return

    # Proceed with forwarded message handling...
```

### Pattern 6: Grouping Seats by Status
**What:** Group SeatAssignment list by status, display with emoji indicators
**When to use:** Main menu display showing all reservation seats

**Example:**
```python
# Source: Combining defaultdict pattern from messages.py + itertools.groupby
from collections import defaultdict
from itertools import groupby
from models.base import SeatStatus

def format_reservation_seats(seats: list[SeatAssignment]) -> str:
    """
    Format all seats grouped by row, with status indicators.

    Returns formatted text:
    Всего мест: 12 | Бронь: 8 | Оплачено: 4

    Ряд 5: 1-3, 5 📌Бронь
    Ряд 5: 7-9 ✅Оплачено
    Ряд 6: 2, 4-6 📌Бронь
    """
    if not seats:
        return "Нет мест"

    # Count by status
    status_counts = defaultdict(int)
    for seat in seats:
        status_counts[seat.status] += 1

    # Summary line
    total = len(seats)
    booked = status_counts[SeatStatus.BOOKED]
    paid = status_counts[SeatStatus.PAID]
    reserved = status_counts[SeatStatus.RESERVED]

    summary = f"Всего мест: {total}"
    if booked:
        summary += f" | 📌Бронь: {booked}"
    if paid:
        summary += f" | ✅Оплачено: {paid}"
    if reserved:
        summary += f" | 🔒Резерв: {reserved}"

    # Group by row and status
    seats_sorted = sorted(seats, key=lambda s: (s.row_number, s.status.value, s.seat_number))

    lines = [summary, ""]

    for row_num, row_group in groupby(seats_sorted, key=lambda s: s.row_number):
        row_seats = list(row_group)

        # Further group by status within row
        for status, status_group in groupby(row_seats, key=lambda s: s.status):
            seat_numbers = [s.seat_number for s in status_group]
            seat_range = format_seat_ranges(seat_numbers)

            # Status emoji
            if status == SeatStatus.BOOKED:
                status_text = "📌Бронь"
            elif status == SeatStatus.PAID:
                status_text = "✅Оплачено"
            else:  # RESERVED
                status_text = "🔒Резерв"

            lines.append(f"Ряд {row_num}: {seat_range} {status_text}")

    return "\n".join(lines)
```

### Anti-Patterns to Avoid
- **Deleting seats one-by-one in loop:** Use batch UPDATE with WHERE IN clause for atomicity
- **Not checking FSM state before context switch:** Leads to data loss if seller accidentally forwards wrong message
- **Using get_json() inside loops:** Pre-generate keyboard JSON once, reuse across messages
- **Forgetting to update last_activity_at:** Reservation timestamp must be updated on every modification

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Consecutive number ranges | Custom loop to detect sequences | `itertools.groupby(enumerate(seats), lambda t: t[0] - t[1])` | Edge cases: single numbers, gaps, negative indices. The enumerate trick is proven pattern |
| Keyboard generation | String concatenation for JSON | VKBottle's `Keyboard` builder | VK API keyboard format has specific structure, color codes, limits (max rows). Builder handles validation |
| FSM state transitions | Manual dictionary in Redis | VKBottle's `StatePeer` with `storage.set()` | Already implemented in Phase 1 with migration logic, maintains consistency |
| Permission checking | Inline conditionals | Database role check with clear error messages | Separation of concerns, easier to test, audit logging needs actor info |
| Seat validation | Re-implement checks | Reuse existing `is_valid_seat()`, `is_valid_row()` from Phase 1 | DRY principle, layout rules are centralized |

**Key insight:** Phase 1 already has robust utilities for seat parsing, validation, and FSM storage. Phase 2 should extend these patterns rather than introducing new approaches.

## Common Pitfalls

### Pitfall 1: itertools.groupby Requires Pre-Sorting
**What goes wrong:** groupby only groups **consecutive** elements with same key value. Unsorted data produces unexpected groups.

**Why it happens:** groupby is iterator-based and processes elements in order received. It doesn't buffer/collect all matching elements like SQL GROUP BY.

**How to avoid:** Always `sorted()` before `groupby()`:
```python
# WRONG - produces multiple groups for same status
for status, group in groupby(seats, key=lambda s: s.status):
    # ...

# RIGHT - sort first
seats_sorted = sorted(seats, key=lambda s: (s.row_number, s.status.value))
for status, group in groupby(seats_sorted, key=lambda s: s.status):
    # ...
```

**Warning signs:**
- Same status appearing multiple times in output
- Groups not appearing in expected order
- "Missing" items that should have been grouped together

### Pitfall 2: VK Emoji Support is Unicode, Not HTML Entities
**What goes wrong:** Using HTML entities like `&amp;#128204;` instead of actual Unicode emoji characters produces literal text in messages.

**Why it happens:** VK messages support Unicode emoji directly. HTML entities are for web browsers, not VK API.

**How to avoid:** Use actual emoji characters in Python strings:
```python
# RIGHT - actual Unicode emoji
status_text = "📌Бронь"  # U+1F4CC (pushpin emoji)

# WRONG - HTML entity
status_text = "&#128204;Бронь"  # displays as literal text
```

**Warning signs:**
- Seeing `&#...;` in bot messages instead of emoji
- Emoji work in web browser but not in VK app

**Reference:** VK uses Apple emoji designs for Emoji 1.0-4.0, native emoji for 5.0+. All Unicode emoji work in messages.

### Pitfall 3: SQLAlchemy update().where() Doesn't Validate Row Count
**What goes wrong:** Batch UPDATE returns rowcount=0 if no rows matched WHERE clause, but doesn't raise exception. Can silently fail to delete seats.

**Why it happens:** SQLAlchemy executes valid SQL - if WHERE doesn't match, that's not an error from database perspective.

**How to avoid:** Always check `result.rowcount` after UPDATE:
```python
result = session.execute(stmt)
session.commit()

if result.rowcount == 0:
    raise DatabaseError("No seats matched deletion criteria")
elif result.rowcount != len(seats):
    logger.warning(f"Expected to delete {len(seats)} seats, actually deleted {result.rowcount}")
```

**Warning signs:**
- Users report "deleted" seats still showing in reservation
- Audit logs show action but database unchanged
- No error message but seats not actually released

### Pitfall 4: Race Condition on Reservation State Check
**What goes wrong:** Check `if has_paid_seats AND not is_admin` → user gets error. But between check and deletion, another process marks seat as PAID. Deletion proceeds incorrectly.

**Why it happens:** Two separate operations (check + delete) without database-level locking.

**How to avoid:** Include status validation in WHERE clause of UPDATE itself:
```python
# Atomic: only deletes seats that are currently BOOKED
stmt = (
    update(SeatAssignment)
    .where(SeatAssignment.reservation_id == reservation_id)
    .where(SeatAssignment.status == SeatStatus.BOOKED)  # <-- validates at DB level
    .where(SeatAssignment.seat_number.in_(seats))
    .values(released_at=datetime.utcnow())
)
result = session.execute(stmt)

if result.rowcount != len(seats):
    # Some seats weren't BOOKED - find which ones
    # Query to get current status and show specific error
```

**Warning signs:**
- Intermittent "permission denied" errors that user can't reproduce
- Different behavior when system is under load vs. idle

### Pitfall 5: Context Switching Without Confirmation Loses Data
**What goes wrong:** Seller is adding seats for Client A, accidentally forwards message from Client B. If bot immediately switches to Client B, Client A's in-progress operation is lost.

**Why it happens:** FSM state is overwritten without saving or prompting.

**How to avoid:** Check current state before accepting new forwarded message (see Pattern 5). Decision from CONTEXT.md requires confirmation prompt.

**Warning signs:**
- Sellers report "lost" seats that were never saved
- Complaints about accidentally switching clients mid-operation

## Code Examples

Verified patterns from official sources and existing codebase:

### VKBottle Multi-Row Keyboard
```python
# Source: https://github.com/vkbottle/vkbottle/blob/master/docs/tutorial/keyboards-attachments.md
from vkbottle import Keyboard, KeyboardButtonColor, Text

keyboard = Keyboard(one_time=False, inline=True)
keyboard.add(Text("Button 1"), color=KeyboardButtonColor.PRIMARY)
keyboard.add(Text("Button 2"), color=KeyboardButtonColor.PRIMARY)
keyboard.row()  # Move to next row
keyboard.add(Text("Button 3"), color=KeyboardButtonColor.SECONDARY)

keyboard_json = keyboard.get_json()
await message.answer("Choose action:", keyboard=keyboard_json)
```

### Consecutive Integer Range Formatting
```python
# Source: https://jonathanchang.org/blog/group-consecutive-number-ranges/
from itertools import groupby
from operator import itemgetter

def format_ranges(numbers: list[int]) -> str:
    """Convert [1, 2, 3, 5, 7, 8, 9] to "1-3, 5, 7-9" """
    ranges = []
    for _, g in groupby(enumerate(numbers), lambda t: t[0] - t[1]):
        group = list(map(itemgetter(1), g))
        if len(group) == 1:
            ranges.append(str(group[0]))
        else:
            ranges.append(f"{group[0]}-{group[-1]}")
    return ", ".join(ranges)
```

### SQLAlchemy Batch UPDATE with WHERE IN
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html
from sqlalchemy import update
from datetime import datetime

stmt = (
    update(SeatAssignment)
    .where(SeatAssignment.reservation_id == reservation_id)
    .where(SeatAssignment.seat_number.in_([5, 6, 7, 8]))
    .where(SeatAssignment.released_at.is_(None))
    .values(released_at=datetime.utcnow())
)

result = session.execute(stmt)
session.commit()
affected_count = result.rowcount  # Number of rows actually updated
```

### Grouping by Multiple Keys with itertools.groupby
```python
# Source: https://note.nkmk.me/en/python-itertools-groupby/
from itertools import groupby

# Group seats by row, then by status within each row
seats_sorted = sorted(seats, key=lambda s: (s.row_number, s.status.value))

for row_num, row_group in groupby(seats_sorted, key=lambda s: s.row_number):
    row_seats = list(row_group)

    for status, status_group in groupby(row_seats, key=lambda s: s.status):
        seat_list = list(status_group)
        # Process seats with same row AND status
```

### Reusing Existing Seat Parser
```python
# Source: /Users/thecattest/things/projects/Tickets/bot/utils/seat_parser.py (Phase 1)
from bot.utils.seat_parser import parse_seats, SeatParseError

# In deletion handler (reuse exact same parser as addition)
try:
    seats = parse_seats(message.text.strip())  # Handles "5-7", "5, 6, 7", "5 6 7"
except SeatParseError as e:
    await message.answer(f"Ошибка ввода: {e}\n\nПопробуйте снова:")
    return
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Text-only keyboard buttons | Callback buttons with event handlers | VKBottle 3.0+ (2021) | Callback buttons enable event-driven UI patterns, but Text buttons are simpler and sufficient for this use case |
| Manual StatePeer serialization | VKBottle's built-in StatePeer model | VKBottle 4.0+ (2023) | Already migrated in Phase 1, storage.py handles both old and new formats |
| SQLAlchemy autocommit mode | Explicit begin/commit with context managers | SQLAlchemy 2.0 (2023) | Requires explicit session.commit(), autocommit removed. Already following in Phase 1 |
| itertools.groupby returns iterator | Same (still iterator) | N/A | Must call list() on groups if needed later - groupby groups are consumed after iteration |

**Deprecated/outdated:**
- **VKBottle 3.x FSM API:** Used separate state storage without StatePeer. Phase 1 already migrated to VKBottle 4.0+ with StatePeer.
- **SQLAlchemy 1.x implicit autocommit:** SQLAlchemy 2.0 requires explicit `session.commit()`. Code already compliant.

## Open Questions

Things that couldn't be fully resolved:

1. **VK inline keyboard row limit**
   - What we know: GitHub docs mention `MAX_INLINE_LINES` exists
   - What's unclear: Exact limit value (likely 10 rows based on VK API general limits)
   - Recommendation: 4-button menu uses 2 rows, well under any reasonable limit. Proceed without concern.

2. **Permission checking for admin role**
   - What we know: Database has `AppUser.role` field (UserRole.ADMIN vs SELLER)
   - What's unclear: How to map VK seller to AppUser (Phase 1 uses `get_default_seller_id()`)
   - Recommendation: For Phase 2, add `is_admin` check helper that queries AppUser by VK ID. Requires VK-to-AppUser mapping table or config file.

3. **Callback buttons vs Text buttons trade-off**
   - What we know: Callback buttons trigger events (`@bot.on.raw_event`), Text buttons are simpler
   - What's unclear: Performance difference, user experience difference in VK app
   - Recommendation: Continue with Text buttons (Phase 1 pattern). Both work, Text is simpler, no migration needed.

## Sources

### Primary (HIGH confidence)
- [VKBottle Keyboards Documentation](https://github.com/vkbottle/vkbottle/blob/master/docs/tutorial/keyboards-attachments.md) - Official keyboard builder patterns
- [VKBottle Message Events Example](https://github.com/vkbottle/vkbottle/blob/master/examples/high-level/message_event.py) - Callback button handling
- [SQLAlchemy 2.0 ORM UPDATE Statements](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html) - Batch updates, WHERE clauses, transaction management
- [Python itertools Documentation](https://docs.python.org/3/library/itertools.html) - groupby specification
- Existing codebase: `bot/utils/seat_parser.py`, `bot/messages.py`, `bot/fsm/storage.py` - Phase 1 patterns

### Secondary (MEDIUM confidence)
- [Jonathan Chang: Group Consecutive Number Ranges](https://jonathanchang.org/blog/group-consecutive-number-ranges/) - itertools.groupby pattern for consecutive integers (verified technique)
- [note.nkmk.me: GROUP BY in Python](https://note.nkmk.me/en/python-itertools-groupby/) - groupby usage with multiple keys
- [GeeksforGeeks: itertools.groupby()](https://www.geeksforgeeks.org/python/itertools-groupby-in-python/) - Examples and sorting requirement
- [Access Control with Decorators](https://levelup.gitconnected.com/access-control-in-python-implementing-authorization-with-decorators-26430a28d530) - Permission checking patterns (general Python pattern, not VKBottle-specific)

### Tertiary (LOW confidence)
- [VK Emojis](https://emojipedia.org/vk) - VK emoji rendering behavior (general info, not API documentation)
- [Unicode Emoji List](https://unicode.org/emoji/charts/full-emoji-list.html) - Emoji character codes (reference, not VK-specific)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in use from Phase 1, versions verified in requirements.txt
- Architecture: HIGH - Patterns verified from official VKBottle docs, SQLAlchemy 2.0 docs, and existing working codebase
- Pitfalls: MEDIUM - Based on general SQLAlchemy/itertools knowledge and common FSM state management issues, not VKBottle-specific documentation
- Range formatting: HIGH - itertools.groupby pattern is well-documented with multiple authoritative sources

**Research date:** 2026-01-24
**Valid until:** 2026-02-23 (30 days - stable technologies, no major version changes expected)

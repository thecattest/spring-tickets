# Phase 5: Просмотр должников и напоминания - Research

**Researched:** 2026-02-18
**Domain:** SQLAlchemy queries, VKBottle proactive messaging, cron scripting
**Confidence:** HIGH

---

## Summary

Phase 5 adds two independent deliverables: the `/debtors` command handler inside the running bot, and a standalone cron script that proactively sends reminder messages to sellers. Both share the same debtor-query logic and the same `db.py` pattern, but operate in different runtimes: one inside the VKBottle polling loop, the other as a plain `asyncio.run()` script.

The debtor query is clearly defined in `DB_SCHEMA.md` (section 5.1): active reservations with at least one BOOKED seat and `last_activity_at <= now() - 7 days`. For SQLite the threshold must be computed in Python as `datetime.utcnow() - timedelta(days=7)` — SQLite's INTERVAL syntax is not supported. The query must JOIN `vk_users` (for buyer name) and use a subquery or correlated EXISTS for the BOOKED-seat count.

The cron script uses VKBottle's `API` class directly without starting a polling bot. The pattern is `api = API(token)` then `await api.messages.send(peer_id=..., message=..., random_id=0)`. This is well-established in the codebase's chosen framework. Error handling for VK API failures (user blocked the bot, etc.) wraps individual sends in try/except so one failure does not abort the whole batch.

**Primary recommendation:** Keep debtor query logic in `bot/utils/db.py` as a new function `get_debtors(seller_id=None)`. The cron script imports from that function and calls VKBottle's API directly. No new libraries needed.

---

## Standard Stack

The project already has everything needed. No new dependencies are required.

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| vkbottle | >=4.0.0 | VK API calls in cron script | Already in requirements.txt |
| sqlalchemy | >=2.0.0 | Debtor DB query | Already in requirements.txt |
| python-dotenv | >=1.0.0 | Load env vars in cron script | Already in requirements.txt |

### No New Libraries Needed
The cron script is scheduled via OS crontab — no Python scheduling library is needed. VKBottle's `API` class handles the proactive sends. All DB access uses `SessionLocal` from `database.py`.

**Installation:** No new packages.

---

## Architecture Patterns

### Recommended Project Structure
```
bot/
├── handlers/
│   └── debtors.py       # /debtors command handler (new)
├── utils/
│   └── db.py            # add get_debtors() function (extend existing)
└── main.py              # register debtors handler (extend existing)

scripts/
└── send_debtors_reminders.py    # standalone cron script (new)
```

### Pattern 1: Debtor Query Function
**What:** Single function in `db.py` that returns debtor records. Takes optional `seller_id` parameter — when None, returns all debtors (admin view); when set, returns only that seller's debtors.

**When to use:** Called by both `/debtors` handler and cron script.

**Key details:**
- The "debtor" threshold is `last_activity_at <= now() - 7 days` AND reservation is ACTIVE AND has at least one unreleased BOOKED seat.
- Debt amount = count of BOOKED seats * SEAT_PRICE (from config).
- Sort by `last_activity_at ASC` (oldest first as per CONTEXT.md).
- JOIN `vk_users` for buyer display name.
- The query must count BOOKED seats per reservation for the display.

**Example (verified against existing db.py patterns and DB_SCHEMA.md):**
```python
# Source: DB_SCHEMA.md section 5.1 + existing db.py patterns
from datetime import datetime, timedelta
from sqlalchemy import select, func, exists
from models.base import ReservationState, SeatStatus

def get_debtors(seller_id=None):
    """
    Return list of debtor records.

    A debtor is an ACTIVE reservation where:
    - last_activity_at <= now() - 7 days
    - at least one seat is BOOKED (unreleased)

    Args:
        seller_id: AppUser.id — if None, returns all (admin view).
                   If set, returns only this seller's reservations.

    Returns:
        List of dicts: {
            'reservation_id': int,
            'buyer_display_name': str,
            'booked_seat_count': int,
            'debt_amount': Decimal,
            'days_since_activity': int,
            'last_activity_at': datetime,
        }
        Sorted by last_activity_at ASC (oldest first).
    """
    threshold = datetime.utcnow() - timedelta(days=7)

    with SessionLocal() as session:
        # Subquery: count BOOKED seats per reservation
        booked_count_sq = (
            select(func.count(SeatAssignment.id))
            .where(SeatAssignment.reservation_id == Reservation.id)
            .where(SeatAssignment.released_at.is_(None))
            .where(SeatAssignment.status == SeatStatus.BOOKED)
            .correlate(Reservation)
            .scalar_subquery()
        )

        stmt = (
            select(
                Reservation.id,
                Reservation.last_activity_at,
                VkUser.display_name,
                booked_count_sq.label("booked_count"),
            )
            .join(VkUser, VkUser.id == Reservation.buyer_vk_user_id)
            .where(Reservation.state == ReservationState.ACTIVE)
            .where(Reservation.last_activity_at <= threshold)
            .where(booked_count_sq > 0)
            .order_by(Reservation.last_activity_at.asc())
        )

        if seller_id is not None:
            stmt = stmt.where(Reservation.sold_by_user_id == seller_id)

        rows = session.execute(stmt).all()

        now = datetime.utcnow()
        result = []
        for row in rows:
            days_since = (now - row.last_activity_at).days
            result.append({
                'reservation_id': row.id,
                'buyer_display_name': row.display_name,
                'booked_seat_count': row.booked_count,
                'debt_amount': Decimal(row.booked_count) * Decimal(SEAT_PRICE),
                'days_since_activity': days_since,
                'last_activity_at': row.last_activity_at,
            })
        return result
```

### Pattern 2: /debtors Command Handler
**What:** A command handler registered in `bot/handlers/debtors.py`, following the exact same pattern as `reserve.py` and `commands.py`.

**When to use:** When a seller or admin types `/debtors` in VK chat.

**Structure:**
```python
# Source: bot/handlers/reserve.py (same pattern)
from vkbottle.bot import Bot, Message
from bot.utils import db
from bot.keyboards import debtors_keyboard  # new keyboard
from models.base import UserRole

async def debtors_command_handler(message: Message):
    """Handle /debtors command."""
    app_user = db.get_app_user_by_vk_id(message.from_id)
    if not app_user:
        await message.answer("Вы не зарегистрированы в системе.")
        return

    # Admin sees all; seller sees only their own
    seller_id = None if app_user.role == UserRole.ADMIN else app_user.id

    debtors = db.get_debtors(seller_id=seller_id)

    if not debtors:
        await message.answer("Должников нет.", keyboard=debtors_keyboard())
        return

    text = format_debtors_list(debtors)
    await message.answer(text, keyboard=debtors_keyboard())


def register_handlers(bot: Bot):
    bot.on.message(text="/debtors")(debtors_command_handler)
```

### Pattern 3: Refresh Button (Обновить)
**What:** Inline keyboard with "Обновить" button. Uses VKBottle's `Keyboard` builder same as all other keyboards. The button text is matched in the handler via `bot.on.message(text="Обновить")` — but this risks collision with global text handlers. Better approach: use state-based routing — after `/debtors` puts user in a DEBTORS_VIEW state, Обновить only fires in that state.

**Decision:** Simplest approach is to make `/debtors` stateless — it only needs one command handler, and "Обновить" re-runs the same query without needing FSM state. To avoid collision, the "Обновить" handler checks whether the user pressed it in a debtors context.

**Recommended simpler approach:** No FSM state needed. Just register `text="Обновить"` as a global handler that re-fetches the debtor list. This is safe because "Обновить" is unlikely to conflict with other flows. Alternatively, call `/debtors` logic on the button press.

**Keyboard:**
```python
# Source: bot/keyboards.py pattern
def debtors_keyboard() -> str:
    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Text("Обновить"), color=KeyboardButtonColor.PRIMARY)
    return keyboard.get_json()
```

### Pattern 4: Standalone Cron Script (VKBottle API without polling)
**What:** A separate Python script that creates a `Bot` instance (or bare `API` instance), queries all sellers with debtors, and sends them messages via `bot.api.messages.send`.

**When to use:** Called by cron every 3 days at 20:00 Moscow time.

**Verified API call pattern (Source: vkbottle easy_bot.py official example):**
```python
# Source: https://github.com/vkbottle/vkbottle/blob/master/examples/high-level/easy_bot.py
await bot.api.messages.send(
    peer_id=vk_user_id,   # seller's vk_user_id (NOT AppUser.id)
    message="...",
    random_id=0,           # 0 is valid per official example
)
```

**Full script pattern:**
```python
# scripts/send_debtors_reminders.py
import asyncio
import logging
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from vkbottle.bot import Bot
from vkbottle import VKAPIError
from bot.config import VK_BOT_TOKEN, SEAT_PRICE
from bot.utils.db import get_debtors, get_all_active_sellers
from database import init_db

logger = logging.getLogger(__name__)

async def main():
    init_db()
    bot = Bot(token=VK_BOT_TOKEN)

    sellers = get_all_active_sellers()  # AppUser[] with vk_user_id IS NOT NULL

    sent_count = 0
    skipped_count = 0
    error_count = 0

    for seller in sellers:
        debtors = get_debtors(seller_id=seller.id)
        if not debtors:
            skipped_count += 1
            continue

        message_text = format_reminder(seller.display_name, debtors)
        try:
            await bot.api.messages.send(
                peer_id=seller.vk_user_id,
                message=message_text,
                random_id=0,
            )
            sent_count += 1
            logger.info(f"Sent reminder to seller {seller.id} ({seller.vk_user_id})")
        except VKAPIError as e:
            error_count += 1
            logger.error(f"VK API error for seller {seller.id}: {e}")
        except Exception as e:
            error_count += 1
            logger.error(f"Unexpected error for seller {seller.id}: {e}")

    logger.info(f"Done. Sent: {sent_count}, Skipped: {skipped_count}, Errors: {error_count}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main())
```

### Pattern 5: get_all_active_sellers() helper
A simple DB query for sellers who can receive VK messages (vk_user_id IS NOT NULL and is_active):
```python
def get_all_active_sellers():
    """Return all active AppUsers with vk_user_id set (can receive VK messages)."""
    with SessionLocal() as session:
        stmt = (
            select(AppUser)
            .where(AppUser.is_active == True)
            .where(AppUser.vk_user_id.is_not(None))
        )
        return list(session.execute(stmt).scalars().all())
```

### Anti-Patterns to Avoid
- **Using SQLite INTERVAL syntax:** `func.now() - interval '7 days'` does not work in SQLite. Always compute the threshold in Python with `timedelta`.
- **Using `bot.run_forever()` in cron script:** The cron script must not start polling. Use `asyncio.run(main())` only.
- **Sending reminders to sellers without vk_user_id:** Some AppUser records may have `vk_user_id IS NULL` — skip them silently.
- **Letting one VK API error abort the batch:** Wrap each `messages.send` in its own try/except.
- **Putting debtor keyboard state in FSM:** Overkill for a stateless view-only command. `/debtors` does not need FSM state.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| VK message sending in cron | Custom HTTP requests to VK API | `vkbottle.bot.Bot.api.messages.send` | Already in stack, handles auth, rate limiting |
| Timezone offset for 20:00 MSK | Custom UTC offset math | System crontab with `TZ=Europe/Moscow` env or just set cron time correctly | Crontab supports `TZ` variable on modern systems |
| "every 3 days" scheduling | Python scheduler library | OS crontab: `0 20 */3 * *` | Simpler, survives script crashes |
| Debt amount calculation | Complex query-level multiplication | Python: `booked_count * SEAT_PRICE` | SEAT_PRICE is in Python config, not DB |

**Key insight:** The debt amount is `count(BOOKED seats) * SEAT_PRICE`. SEAT_PRICE lives in `bot/config.py` (env var). Compute it in Python after the query, not inside SQL.

---

## Common Pitfalls

### Pitfall 1: datetime.utcnow() vs timezone-aware datetimes
**What goes wrong:** The DB stores datetimes via `datetime.utcnow()` (naive UTC). If the script runs with a TZ-aware datetime from `datetime.now(tz=...)`, the comparison breaks because SQLite sees a TZ-annotated string vs a plain UTC string.
**Why it happens:** SQLite stores datetimes as text. Mixing aware/naive datetimes creates mismatches.
**How to avoid:** Use `datetime.utcnow() - timedelta(days=7)` consistently, matching how existing code stores datetimes. Do NOT use `datetime.now(tz=timezone.utc)` unless the whole codebase switches.
**Warning signs:** Query returns 0 rows even when old BOOKED reservations exist.

### Pitfall 2: Seller has no vk_user_id
**What goes wrong:** Cron script tries to send VK message to a seller with `vk_user_id = None` — VK API rejects with error.
**Why it happens:** AppUser allows `vk_user_id = NULL` (column is nullable, see `models/user.py`).
**How to avoid:** `get_all_active_sellers()` filters `WHERE vk_user_id IS NOT NULL`. Log skipped sellers.

### Pitfall 3: Admin also appears in seller reminder loop
**What goes wrong:** Admins see all debtors in `/debtors`, but for cron reminders, you might send them a message containing ALL debtors — could be overwhelming or wrong.
**Why it happens:** `get_debtors(seller_id=None)` returns everything.
**How to avoid:** Cron script iterates sellers only (role=SELLER). Admins can check via `/debtors` manually. If admins should also get reminders, treat them as sellers (pass their AppUser.id as seller_id to see only their created reservations). Decided: cron reminds sellers only (those with role=SELLER or any user with vk_user_id set — per the CONTEXT.md, the cron sends to bileteers, not admins separately).

**Resolution:** Cron sends reminders to ALL users who have `vk_user_id IS NOT NULL` and `is_active = True`. Each user's reminder contains only their own debtors (`sold_by_user_id = user.id`). Admins who want global view use `/debtors`.

### Pitfall 4: "Обновить" text button collision
**What goes wrong:** If another handler globally listens for text "Обновить", pressing the button during another flow triggers unexpected behavior.
**Why it happens:** VKBottle routes by text match globally unless state-filtered.
**How to avoid:** Either (a) register handler as `bot.on.message(text="Обновить")` — since no other flow uses this text, it's safe; or (b) check that this text is unique across all handlers before shipping. Currently no other handler uses "Обновить".

### Pitfall 5: random_id=0 in batch sends
**What goes wrong:** VK API documentation says random_id prevents duplicate sends. Using `random_id=0` means the deduplication window is per-session, not permanent. In practice for cron batch sends this is fine — official VKBottle examples use `random_id=0`.
**How to avoid:** Using `random_id=0` is acceptable for cron batch. If deduplication is needed (retry scenarios), use `random.randint(1, 2**31)`.

### Pitfall 6: Counting days with integer division vs timedelta.days
**What goes wrong:** `(now - last_activity_at).days` returns the number of complete days. This is correct for "how many days since last activity."
**Why it matters:** A reservation from 6.9 days ago shows as 6 days, not 7. The threshold query uses `<= threshold` which is `<= now - 7 days` — so the reservation must be at least 7 complete days old to appear. Consistent.

---

## Code Examples

### Debtor list message format (for /debtors)
```python
# Verified against existing messages.py style (no external source needed)
def format_debtors_list(debtors: list) -> str:
    """Format debtors list for /debtors command output."""
    lines = [f"Должники ({len(debtors)}):"]
    lines.append("")
    for d in debtors:
        lines.append(
            f"{d['buyer_display_name']}\n"
            f"  Мест: {d['booked_seat_count']} | "
            f"Долг: {d['debt_amount']} руб. | "
            f"Дней: {d['days_since_activity']}"
        )
    return "\n".join(lines)
```

### Reminder message format (for cron script)
```python
def format_reminder(seller_display_name: str, debtors: list) -> str:
    """Format reminder message sent to seller by cron."""
    lines = [f"Напоминание о должниках ({len(debtors)}):"]
    lines.append("")
    for d in debtors:
        lines.append(
            f"{d['buyer_display_name']} — "
            f"{d['booked_seat_count']} мест, "
            f"{d['debt_amount']} руб., "
            f"{d['days_since_activity']} дн. без активности"
        )
    return "\n".join(lines)
```

### Crontab entry
```bash
# Run every 3 days at 20:00 Moscow time
# If server is in UTC, 20:00 MSK = 17:00 UTC (winter) / 17:00 UTC (MSK = UTC+3)
# Use TZ variable for clarity:
TZ=Europe/Moscow
0 20 */3 * * /path/to/venv/bin/python /path/to/project/scripts/send_debtors_reminders.py >> /var/log/debtors_reminders.log 2>&1
```

### VKBottle VKAPIError import
```python
# Source: vkbottle easy_bot.py official example
from vkbottle import VKAPIError

try:
    await bot.api.messages.send(peer_id=..., message=..., random_id=0)
except VKAPIError[901]:
    # Error 901: Can't send messages to this user (privacy settings)
    logger.error("Can't send to user — privacy settings")
except VKAPIError as e:
    logger.error(f"VK API error {e.code}: {e.description}")
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Polling-only bot sends | `Bot.api.messages.send()` from any async context | Cron script can send without running polling |
| Python scheduler (APScheduler) | OS crontab | No extra dependency, survives crashes |

**Not applicable / No deprecated patterns:** The codebase is new enough that there are no migration concerns.

---

## Open Questions

1. **Admin inclusion in cron reminders**
   - What we know: CONTEXT.md says "recipient is билетер (seller), not client"
   - What's unclear: Should admins who also have `vk_user_id` receive reminders for reservations they personally created (`sold_by_user_id = admin.id`)?
   - Recommendation: Yes — `get_all_active_sellers()` should include ALL AppUsers with `vk_user_id IS NOT NULL`, regardless of role. Each gets their own debtor sublist. Admin's `/debtors` view shows all.

2. **Cron timing: absolute UTC or TZ-relative**
   - What we know: 20:00 МСК is UTC+3, so 17:00 UTC in standard time
   - What's unclear: Whether the server is in MSK timezone or UTC
   - Recommendation: Use `TZ=Europe/Moscow` in crontab entry for portability. Document this in crontab comments.

3. **"Обновить" keyboard after /debtors — does it need a persistent state?**
   - What we know: All other stateful keyboards use FSM states (MAIN_MENU, RESERVE_ACTION, etc.)
   - What's unclear: Whether a user pressing "Обновить" while in another FSM state would cause issues
   - Recommendation: Register `/debtors` as a command that clears/ignores current state (same as `/cancel` does). "Обновить" handler is registered globally with no state requirement, same as `/start` and `/help`. This is the simplest approach consistent with the codebase.

---

## Sources

### Primary (HIGH confidence)
- `bot/utils/db.py` — Existing debtor query patterns, `SessionLocal` usage, `datetime.utcnow()` throughout
- `models/reservation.py` — `last_activity_at` field confirmed, indexes confirmed
- `models/user.py` — `vk_user_id` is nullable, `role` is UserRole enum
- `models/seat_assignment.py` — `status`, `released_at`, `reservation_id` fields
- `DB_SCHEMA.md` section 5.1 — Exact SQL for debtor query documented by project authors
- `bot/handlers/reserve.py` — Command handler registration pattern with storage
- `bot/handlers/commands.py` — Stateless command handler pattern (no FSM for /start, /help)
- `bot/keyboards.py` — Keyboard builder pattern with VKBottle `Keyboard`/`Text`/`KeyboardButtonColor`
- `bot/config.py` — `SEAT_PRICE`, `VK_BOT_TOKEN` env vars
- `database.py` — `SessionLocal`, `init_db` confirmed

### Secondary (MEDIUM confidence)
- [VKBottle easy_bot.py official example](https://github.com/vkbottle/vkbottle/blob/master/examples/high-level/easy_bot.py) — `bot.api.messages.send(peer_id=..., message=..., random_id=0)` pattern verified
- [VKBottle first-bot.md docs](https://github.com/vkbottle/vkbottle/blob/master/docs/tutorial/first-bot.md) — `random_id` is required; `random_id=0` is acceptable
- [VKBottle FAQ](https://vkbottle.readthedocs.io/ru/latest/tutorial/faq/) — `API` class can be used standalone without polling

### Tertiary (LOW confidence)
- SQLite timedelta filtering: multiple community sources confirm Python-side `timedelta` calculation is the correct approach for SQLite (not SQL INTERVAL functions)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in requirements.txt; no new dependencies
- Architecture: HIGH — patterns verified directly in existing codebase files
- DB query: HIGH — query schema documented in DB_SCHEMA.md by project authors
- VKBottle proactive send: HIGH — verified in official vkbottle example code
- SQLite datetime filter: MEDIUM — community consensus verified; existing codebase uses `datetime.utcnow()` throughout confirming approach
- Pitfalls: HIGH — derived from reading actual code (nullable vk_user_id, UTC datetime usage)

**Research date:** 2026-02-18
**Valid until:** 2026-03-20 (stable stack, 30-day window)

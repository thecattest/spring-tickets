# Phase 3: Регистрация оплаты - Research

**Researched:** 2026-02-17
**Domain:** VKBottle FSM payment flow, SQLAlchemy, existing codebase integration
**Confidence:** HIGH (all findings from direct codebase inspection + VKBottle source)

---

## Summary

Phase 3 implements the full payment recording flow: triggering via forwarded receipt or [Оплата] button,
asking how many seats to mark as paid, deterministically selecting seats (row ASC, seat ASC), and updating
DB records. The codebase patterns from Phases 1-2 are mature and directly usable.

The critical architectural question - "how to distinguish forwarded receipt from forwarded client message" -
has a clean answer: use VKBottle's combined state+func rule matching. The existing `func=lambda msg:
bool(msg.fwd_messages)` global handler fires for any state. A more specific handler registered with BOTH
`state=BotState.PAYMENT_QUANTITY` AND `func=lambda msg: bool(msg.fwd_messages)` will fire first in the
PAYMENT_QUANTITY state because handlers are evaluated in registration order and are blocking by default.

**Primary recommendation:** Use `PAYMENT_QUANTITY` FSM state + combined state/func rules for the forwarded
receipt variant. For the [Оплата] button variant, transition to `PAYMENT_QUANTITY` from within
`main_menu_handler`. Both paths converge at the same quantity-selection UI.

One design blocker: the `Payment` model has `vk_message_url` and `vk_message_ts` as `NOT NULL`, but the
[Оплата] button flow has no forwarded receipt. The planner must decide how to handle this (nullable fields or
sentinel values).

---

## Standard Stack

All libraries are already installed and in use. No new dependencies required.

### Core (already in use)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| vkbottle | 4.6.2 | VK Bot framework, FSM, keyboards | Verified from pip show |
| SQLAlchemy | existing | ORM, DB operations | Session pattern already established |
| redis-py (async) | existing | FSM storage | RedisStorage class already implemented |

### Models already defined
| Model | File | Status |
|-------|------|--------|
| Payment | models/payment.py | EXISTS - but has NOT NULL constraint issue (see below) |
| PaymentSeat | models/payment.py | EXISTS - unique index on seat_assignment_id |
| SeatAssignment | models/seat_assignment.py | EXISTS - has status enum (BOOKED/PAID/RESERVED) |
| AuditLog | models/audit.py | EXISTS - used by all existing operations |

**Installation:** No new packages needed.

---

## Architecture Patterns

### Recommended Project Structure (new files for Phase 3)

```
bot/handlers/
├── payment.py          # NEW: payment flow handlers (forwarded receipt + button flow)
bot/utils/
├── db.py               # EXTEND: add record_payment() function
bot/fsm/
├── states.py           # EXTEND: add PAYMENT_QUANTITY state
bot/
├── keyboards.py        # EXTEND: add payment_quantity_keyboard(booked_count) function
├── messages.py         # EXTEND: add format_payment_confirmation() function
```

### Pattern 1: VKBottle Handler Registration Order (CRITICAL)

**What:** VKBottle handlers are evaluated in registration order. The first matching handler fires and
(because blocking=True by default) stops further processing.

**The forwarded message disambiguation:** In reservation.py, the global forwarded handler is:
```python
# From reservation.py line 406 - fires for ANY state
bot.on.message(func=lambda msg: bool(msg.fwd_messages))(forwarded_with_storage)
```

In payment.py, register the PAYMENT_QUANTITY forwarded handler BEFORE the global one:
```python
# In payment.register_handlers(bot) - must be called BEFORE reservation.register_handlers(bot)
bot.on.message(state=BotState.PAYMENT_QUANTITY, func=lambda msg: bool(msg.fwd_messages))(receipt_in_payment_with_storage)

# NOTE: This catches "forwarded message while awaiting payment quantity" - e.g. seller accidentally
# forwards something. Not the primary receipt trigger. See Pattern 2.
```

**The correct trigger sequence:**
- Variant A: Seller is IDLE or MAIN_MENU, forwards receipt -> this is already caught by the existing
  `forwarded_message_handler`. The handler needs a new branch: when in MAIN_MENU, a forwarded message
  should start the payment flow, NOT the client-selection flow.
- Variant B: [Оплата] button in MAIN_MENU -> `main_menu_handler` already routes "Оплата" to a placeholder.

**Revised understanding of Variant A trigger:** The existing `forwarded_message_handler` needs modification.
When the seller is in MAIN_MENU state and forwards a message, the current code at line 67 treats all
non-IDLE states as "working with another client" and shows context switch. This is wrong for Variant A.

**The fix:** In `forwarded_message_handler`, add a branch for `current_state == "main_menu"`:
```python
if current_state == "main_menu":
    # In main menu = forwarding a receipt for the current client
    await start_payment_from_receipt(message, storage, current_context, buyer_vk_id)
    return
```

### Pattern 2: FSM State for Payment Quantity Selection

**New state:** `PAYMENT_QUANTITY` - awaiting quantity button press from seller.

**State context payload** (stored in Redis):
```python
{
    "reservation_id": int,
    "buyer_vk_user_id": int,
    "buyer_vk_api_id": int,
    "buyer_display_name": str,
    "from_main_menu": True,
    # Payment-specific:
    "booked_seat_count": int,       # total BOOKED seats for validation
    "receipt_vk_message_url": str,  # URL of forwarded receipt (or sentinel for button flow)
    "receipt_vk_message_ts": str,   # ISO timestamp of receipt (or sentinel for button flow)
    "buyer_vk_id_for_receipt": int, # VK API ID of receipt author (for Variant A)
}
```

**State transition diagram:**
```
MAIN_MENU + forward receipt  -> (validate receipt author has active reservation) -> PAYMENT_QUANTITY
MAIN_MENU + press [Оплата]   -> PAYMENT_QUANTITY
PAYMENT_QUANTITY + [1..N]    -> record_payment() -> MAIN_MENU (with updated seat list)
PAYMENT_QUANTITY + [Отмена]  -> MAIN_MENU
```

### Pattern 3: Dynamic Keyboard for Quantity Selection

**What:** Build keyboard buttons dynamically from the count of BOOKED seats.

**Pattern from existing keyboards.py:**
```python
# Source: bot/keyboards.py - follows same Keyboard() builder pattern
from vkbottle import Keyboard, KeyboardButtonColor, Text

def payment_quantity_keyboard(booked_count: int) -> str:
    """
    Build payment quantity keyboard.

    Layout (up to 5 buttons per row for readability):
    [1] [2] [3] [Все 5]          (if booked_count <= 4)
    [1] [2] [3] [4] [5] [Все 7]  (if booked_count <= 6)
    etc.

    Max VK keyboard: 10 buttons per row (enforced by VK API)
    Practical limit: fit on screen, so max ~5 numbers + "All N" per row.
    """
    keyboard = Keyboard(one_time=False, inline=True)

    # Individual quantity buttons (1 to booked_count-1)
    buttons_on_row = 0
    for i in range(1, booked_count):
        if buttons_on_row == 5:
            keyboard.row()
            buttons_on_row = 0
        keyboard.add(Text(str(i)), color=KeyboardButtonColor.PRIMARY)
        buttons_on_row += 1

    # "Все N" button (pay all)
    if buttons_on_row == 5:
        keyboard.row()
    keyboard.add(Text(f"Все {booked_count}"), color=KeyboardButtonColor.POSITIVE)

    # Cancel button on new row
    keyboard.row()
    keyboard.add(Text("Отмена"), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()
```

**VK API keyboard limits (HIGH confidence, verified in VKBottle source):**
- Max 10 buttons per row (VK API constraint)
- Max 10 rows per keyboard
- Inline keyboards: same limits apply
- For booked_count > 10: use rows of 5 to stay readable

### Pattern 4: record_payment() Database Function

**Exact implementation based on BOT_SPEC + existing db.py patterns:**

```python
# Source: bot/utils/db.py - follows existing SessionLocal() + AuditLog pattern
from models.payment import Payment, PaymentSeat

class InsufficientSeatsError(DatabaseError):
    """Raised when requested seat_count exceeds available BOOKED seats."""
    def __init__(self, requested: int, available: int):
        self.requested = requested
        self.available = available
        super().__init__(f"Requested {requested} seats but only {available} BOOKED available")


def record_payment(
    reservation_id: int,
    seat_count: int,
    payment_amount: Decimal,
    user_id: int,
    vk_message_url: str,
    vk_message_ts: datetime,
    note: Optional[str] = None,
) -> Payment:
    """
    Record payment for N seats (deterministic selection: row ASC, seat ASC).

    Args:
        reservation_id: Reservation to mark
        seat_count: How many BOOKED seats to mark PAID
        payment_amount: Total amount paid (seat_count * SEAT_PRICE)
        user_id: AppUser.id of the seller recording payment
        vk_message_url: URL of forwarded receipt (or placeholder for button flow)
        vk_message_ts: Timestamp of receipt message (or placeholder for button flow)
        note: Optional note

    Returns:
        Created Payment record

    Raises:
        InsufficientSeatsError: If seat_count > number of BOOKED seats
        DatabaseError: If operation fails
    """
    with SessionLocal() as session:
        try:
            # Fetch BOOKED seats deterministically (row ASC, seat ASC)
            stmt = (
                select(SeatAssignment)
                .where(SeatAssignment.reservation_id == reservation_id)
                .where(SeatAssignment.status == SeatStatus.BOOKED)
                .where(SeatAssignment.released_at.is_(None))
                .order_by(
                    SeatAssignment.row_number.asc(),
                    SeatAssignment.seat_number.asc(),
                )
                .limit(seat_count)
            )
            seats = session.execute(stmt).scalars().all()

            if len(seats) < seat_count:
                # Count actual available
                count_stmt = (
                    select(SeatAssignment)
                    .where(SeatAssignment.reservation_id == reservation_id)
                    .where(SeatAssignment.status == SeatStatus.BOOKED)
                    .where(SeatAssignment.released_at.is_(None))
                )
                all_booked = session.execute(count_stmt).scalars().all()
                raise InsufficientSeatsError(seat_count, len(all_booked))

            # Create Payment record
            payment = Payment(
                reservation_id=reservation_id,
                recorded_by_user_id=user_id,
                vk_message_url=vk_message_url,
                vk_message_ts=vk_message_ts,
                payment_amount=payment_amount,
                seat_count=seat_count,
                note=note,
            )
            session.add(payment)
            session.flush()  # Get payment.id without committing

            # Link seats to payment and mark as PAID
            for seat in seats:
                seat.status = SeatStatus.PAID
                payment_seat = PaymentSeat(
                    payment_id=payment.id,
                    seat_assignment_id=seat.id,
                )
                session.add(payment_seat)

            # Update reservation last_activity_at
            reservation_stmt = select(Reservation).where(Reservation.id == reservation_id)
            reservation = session.execute(reservation_stmt).scalar_one()
            reservation.last_activity_at = datetime.utcnow()

            session.commit()

            # Refresh to get final state
            session.refresh(payment)

            # Audit log
            paid_seat_info = [
                {"row": s.row_number, "seat": s.seat_number, "id": s.id}
                for s in seats
            ]
            audit = AuditLog(
                actor_type=ActorType.USER,
                actor_user_id=user_id,
                action_type="payment_recorded",
                entity_type="payment",
                entity_id=str(payment.id),
                payload={
                    "reservation_id": reservation_id,
                    "seat_count": seat_count,
                    "payment_amount": str(payment_amount),
                    "seats": paid_seat_info,
                    "vk_message_url": vk_message_url,
                }
            )
            session.add(audit)
            session.commit()

            logger.info(
                f"Recorded payment {payment.id} for reservation {reservation_id}: "
                f"{seat_count} seats, amount={payment_amount}"
            )
            return payment

        except (InsufficientSeatsError, DatabaseError):
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record payment: {e}")
            raise DatabaseError(f"Failed to record payment: {e}")
```

### Pattern 5: handler registration order in main.py

**Current order in main.py:**
```python
commands.register_handlers(bot)
reservation.register_handlers(bot)
menu.register_handlers(bot)
deletion.register_handlers(bot)
```

**Required for Phase 3:** Add `payment.register_handlers(bot)` BEFORE `reservation.register_handlers(bot)`
so that the payment receipt handler takes priority over the global forwarded handler.

However - see "Anti-Patterns" section - actually, the receipt trigger is in the MAIN_MENU state. The
forwarded_message_handler currently has an early-exit for non-IDLE states. The cleanest solution is to
modify `forwarded_message_handler` directly to handle the MAIN_MENU case, rather than relying on
handler order. This avoids registration-order fragility.

### Recommended Project Structure for handler file
```python
# bot/handlers/payment.py

async def start_payment_from_receipt(
    message: Message, storage: RedisStorage,
    current_context: dict, buyer_vk_id: int
):
    """Called from forwarded_message_handler when state == MAIN_MENU."""
    ...

async def start_payment_from_button(message: Message, storage: RedisStorage):
    """Called from main_menu_handler when text == 'Оплата'."""
    ...

async def payment_quantity_handler(message: Message, storage: RedisStorage):
    """Handle button press in PAYMENT_QUANTITY state."""
    ...

def register_handlers(bot: Bot):
    bot.on.message(state=BotState.PAYMENT_QUANTITY)(payment_quantity_with_storage)
```

### Anti-Patterns to Avoid

- **Relying purely on handler registration order for state disambiguation:** VKBottle evaluates handlers
  in registration order, but this is fragile. Prefer explicit state checks inside handlers (like the
  existing `if current_state != "idle":` pattern in forwarded_message_handler).
- **Opening multiple SQLAlchemy sessions:** The existing pattern always uses `with SessionLocal() as
  session:`. The record_payment() function must do all operations in ONE session (session.flush() before
  session.commit() to get payment.id).
- **Not importing Payment/PaymentSeat in db.py:** These models exist but are NOT currently imported in
  db.py. Add imports at the top.
- **Building keyboard without checking booked_count == 0:** If somehow booked_count is 0, the keyboard
  would have only [Отмена]. This edge case must be handled before showing the keyboard.
- **Assuming `Все {N}` button text is unique:** The quantity handler must parse both numeric strings
  ("1", "2", ...) AND the "Все N" pattern. Use `text.startswith("Все ")` + int parsing.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deterministic seat selection | Custom sort/filter logic | SQLAlchemy `.order_by().limit()` | Already specified in BOT_SPEC, SQLAlchemy handles it atomically within session |
| Keyboard row/column layout | Custom layout code | `Keyboard().row()` calls | VKBottle Keyboard builder already does this |
| Payment atomicity | Manual try/commit/rollback | SQLAlchemy session with `session.flush()` then `session.commit()` | Established pattern in all existing db.py functions |
| Audit logging | Custom log format | AuditLog model (existing pattern) | Already used in all 4 existing operations |
| Seat status check | Re-query after update | Query BEFORE update, update in same session | Avoids race condition window |

---

## Common Pitfalls

### Pitfall 1: Payment Model NOT NULL Fields in Button Flow

**What goes wrong:** `Payment.vk_message_url` and `Payment.vk_message_ts` are `nullable=False` in the
model. When payment is recorded via the [Оплата] button (Variant B), there is no forwarded receipt,
so these fields have no natural values.

**Why it happens:** The model was designed with receipt-based payment in mind (Variant A).

**How to avoid - three options (choose one):**
1. **Make fields nullable for Variant B** - Change model: `vk_message_url: Mapped[Optional[str]]`, add
   Alembic migration. Clean but requires schema change.
2. **Use sentinel placeholder** - For button flow, set `vk_message_url = ""` and
   `vk_message_ts = datetime.utcnow()`. Dirty but schema-compatible. Needs clear documentation.
3. **Add `trigger_type` column** - `trigger_type: Mapped[str]` with values "receipt" or "button".
   Best for audit/reporting but requires migration.

**Recommendation:** Option 1 (make nullable) is the cleanest. This is a schema evolution that was
anticipated. Add Alembic migration.

**Warning signs:** `IntegrityError: NOT NULL constraint failed: payments.vk_message_url` during testing.

### Pitfall 2: Forwarded Message in MAIN_MENU Currently Goes to Context Switch

**What goes wrong:** `forwarded_message_handler` at line 67 checks `if current_state != "idle"` and
routes to context switch confirmation for ALL non-idle states. A seller in MAIN_MENU state forwarding
a receipt would get a context switch prompt, not a payment prompt.

**Why it happens:** The Phase 2 handler was written before Phase 3 existed.

**How to avoid:** Add explicit MAIN_MENU branch in `forwarded_message_handler`:
```python
if current_state == "main_menu":
    # Forwarding receipt for current client's reservation
    await start_payment_from_receipt(message, storage, current_context, buyer_vk_id)
    return
elif current_state != "idle":
    # Working with another client - context switch
    ...
```

**Warning signs:** Seller gets "Переключиться на ...?" prompt when they forward a receipt.

### Pitfall 3: "Все N" Button Text Parsing

**What goes wrong:** The PAYMENT_QUANTITY state handler receives button text like "Все 3". Naively
checking `int(text)` will throw ValueError.

**How to avoid:**
```python
text = message.text.strip()
booked_count = context.get("booked_seat_count")

if text == "Отмена":
    # Return to main menu
elif text.startswith("Все "):
    quantity = booked_count  # Trust the context, not the text number
elif text.isdigit():
    quantity = int(text)
    if quantity < 1 or quantity > booked_count:
        # Show error
else:
    # Unknown input, re-show keyboard
```

**Warning signs:** `ValueError` in payment handler logs.

### Pitfall 4: Validation Before Showing Payment UI

**What goes wrong:** Clicking [Оплата] or forwarding receipt when there are NO BOOKED seats (all are
already PAID or reservation is empty). The payment flow would show a keyboard with only [Отмена].

**How to avoid:** Before transitioning to PAYMENT_QUANTITY, check booked count:
```python
booked_seats = [s for s in seats if s.status == SeatStatus.BOOKED]
if not booked_seats:
    await message.answer(
        "Нет мест для оплаты. Все места уже оплачены.",
        keyboard=main_menu_keyboard()
    )
    return
```

**Warning signs:** Empty keyboard or keyboard with just [Отмена].

### Pitfall 5: Receipt Belongs to a DIFFERENT Client

**What goes wrong (Variant A receipt):** The seller is in MAIN_MENU for client A, then forwards a
receipt from client B. The code needs to check that the receipt author (buyer_vk_id from forwarded
message) matches the current context's buyer.

**How to avoid:** In `start_payment_from_receipt`:
```python
current_buyer_vk_api_id = current_context.get("buyer_vk_api_id")
if buyer_vk_id != current_buyer_vk_api_id:
    # Receipt is from a different person than the current client
    await message.answer(
        f"Получен чек от {display_name}, но вы работаете с {current_buyer_display_name}.\n"
        f"Используйте кнопку [Оплата] для текущего клиента.",
        keyboard=main_menu_keyboard()
    )
    return
```

### Pitfall 6: PaymentSeat Unique Constraint Violation on Retry

**What goes wrong:** `payment_seats` has `Index("payment_seats_one_payment_per_seat",
"seat_assignment_id", unique=True)`. If a seat is somehow selected twice (shouldn't happen with
BOOKED-only query), SQLAlchemy raises IntegrityError.

**How to avoid:** The BOOKED-only query with `.where(SeatAssignment.status == SeatStatus.BOOKED)` and
the status update to PAID within the same session prevents this. The unique constraint is a safety net.

---

## Code Examples

### Example 1: Triggering Payment from [Оплата] Button (in menu.py)

```python
# Source: bot/handlers/menu.py - extends existing elif text == "Оплата": branch
# bot/handlers/payment.py must be imported

elif text == "Оплата":
    try:
        seats = db.get_reservation_seats(reservation_id)
        booked_seats = [s for s in seats if s.status == SeatStatus.BOOKED]

        if not booked_seats:
            await message.answer(
                "Нет мест для оплаты. Все места уже оплачены.",
                keyboard=main_menu_keyboard()
            )
            return

        # Import from payment handler
        from bot.handlers.payment import start_payment_from_button
        await start_payment_from_button(message, storage, context, booked_seats)

    except db.DatabaseError as e:
        logger.error(f"Error starting payment: {e}")
        await message.answer("Ошибка. Попробуйте позже.", keyboard=main_menu_keyboard())
```

### Example 2: PAYMENT_QUANTITY State Handler

```python
# Source: bot/handlers/payment.py (new file)
async def payment_quantity_handler(message: Message, storage: RedisStorage):
    text = message.text.strip()
    context = await storage.get_context(message.from_id)

    reservation_id = context.get("reservation_id")
    booked_count = context.get("booked_seat_count")
    buyer_vk_user_id = context.get("buyer_vk_user_id")
    buyer_vk_api_id = context.get("buyer_vk_api_id")
    buyer_display_name = context.get("buyer_display_name")
    vk_message_url = context.get("receipt_vk_message_url", "")
    vk_message_ts_str = context.get("receipt_vk_message_ts")

    if text == "Отмена":
        await show_main_menu(message, storage, reservation_id, buyer_vk_user_id,
                             buyer_display_name, buyer_vk_api_id)
        return

    # Parse quantity
    if text.startswith("Все "):
        quantity = booked_count
    elif text.isdigit():
        quantity = int(text)
    else:
        await message.answer("Нажмите одну из кнопок:", keyboard=payment_quantity_keyboard(booked_count))
        return

    # Validate range
    if quantity < 1 or quantity > booked_count:
        await message.answer(
            f"Введено количество {quantity}, но доступно только {booked_count} мест для оплаты.\n"
            f"Введите количество от 1 до {booked_count}:",
            keyboard=payment_quantity_keyboard(booked_count)
        )
        return

    # Record payment
    try:
        seller_id = db.get_default_seller_id()
        payment_amount = Decimal(quantity * SEAT_PRICE)
        vk_message_ts = datetime.fromisoformat(vk_message_ts_str) if vk_message_ts_str else datetime.utcnow()

        payment = db.record_payment(
            reservation_id=reservation_id,
            seat_count=quantity,
            payment_amount=payment_amount,
            user_id=seller_id,
            vk_message_url=vk_message_url,
            vk_message_ts=vk_message_ts,
        )

        # Build confirmation message
        all_seats = db.get_reservation_seats(reservation_id)
        paid_seats = [s for s in all_seats if s.status == SeatStatus.PAID]
        remaining_booked = [s for s in all_seats if s.status == SeatStatus.BOOKED]

        confirmation = (
            f"Оплачено {quantity} мест.\n"
            f"Сумма: {payment_amount} руб.\n\n"
        )
        if remaining_booked:
            confirmation += f"Осталось к оплате: {len(remaining_booked)} мест."

        await message.answer(confirmation, keyboard=get_empty_keyboard())
        await show_main_menu(message, storage, reservation_id, buyer_vk_user_id,
                             buyer_display_name, buyer_vk_api_id)

    except db.InsufficientSeatsError as e:
        await message.answer(
            f"Ошибка: запрошено {e.requested} мест, но доступно только {e.available}.",
            keyboard=payment_quantity_keyboard(booked_count)
        )
    except db.DatabaseError as e:
        logger.error(f"Failed to record payment: {e}")
        await message.answer("Ошибка при записи оплаты. Попробуйте позже.")
        await show_main_menu(message, storage, reservation_id, buyer_vk_user_id,
                             buyer_display_name, buyer_vk_api_id)
```

### Example 3: Forwarded Receipt in MAIN_MENU (modification to reservation.py)

```python
# Source: bot/handlers/reservation.py - forwarded_message_handler modification
# Add this branch at line ~67, BEFORE the generic "not idle" check:

if current_state == "main_menu":
    current_context = state_peer.payload
    current_buyer_vk_api_id = current_context.get("buyer_vk_api_id")

    if buyer_vk_id == current_buyer_vk_api_id:
        # Receipt from current client - start payment flow
        from bot.handlers.payment import start_payment_from_receipt
        await start_payment_from_receipt(message, storage, current_context,
                                         buyer_vk_id, display_name)
    else:
        current_buyer_display_name = current_context.get("buyer_display_name", "текущего клиента")
        await message.answer(
            f"Получен чек от {display_name}, но вы работаете с {current_buyer_display_name}.\n"
            f"Используйте кнопку [Оплата] для текущего клиента.",
            keyboard=main_menu_keyboard()  # keep current state
        )
    return
```

### Example 4: start_payment_from_receipt / start_payment_from_button in payment.py

```python
# Source: bot/handlers/payment.py (new file)
async def start_payment_from_receipt(
    message: Message,
    storage: RedisStorage,
    current_context: dict,
    buyer_vk_id: int,
    display_name: str,
):
    """Entry point: seller forwarded a receipt from current client."""
    reservation_id = current_context.get("reservation_id")
    seats = db.get_reservation_seats(reservation_id)
    booked_seats = [s for s in seats if s.status == SeatStatus.BOOKED]

    if not booked_seats:
        await message.answer(
            "Нет мест для оплаты. Все места уже оплачены.",
            keyboard=main_menu_keyboard()
        )
        return

    booked_count = len(booked_seats)
    booked_summary = format_booked_seats(booked_seats)  # helper in messages.py

    # Build receipt URL from forwarded message
    fwd = message.fwd_messages[0]
    vk_message_url = f"https://vk.com/im?sel={buyer_vk_id}&msgid={fwd.id}"
    vk_message_ts = datetime.fromtimestamp(fwd.date) if hasattr(fwd, 'date') else datetime.utcnow()

    await message.answer(
        f"Получен чек от {display_name}. Бронь:\n"
        f"{booked_summary}\n\n"
        f"Сколько мест оплачено?",
        keyboard=payment_quantity_keyboard(booked_count)
    )

    await storage.set(
        message.from_id,
        BotState.PAYMENT_QUANTITY,
        **current_context,
        booked_seat_count=booked_count,
        receipt_vk_message_url=vk_message_url,
        receipt_vk_message_ts=vk_message_ts.isoformat(),
    )


async def start_payment_from_button(
    message: Message,
    storage: RedisStorage,
    current_context: dict,
    booked_seats: list,
):
    """Entry point: seller pressed [Оплата] button."""
    booked_count = len(booked_seats)
    booked_summary = format_booked_seats(booked_seats)

    await message.answer(
        f"Бронь:\n{booked_summary}\n\nСколько мест оплачено?",
        keyboard=payment_quantity_keyboard(booked_count)
    )

    await storage.set(
        message.from_id,
        BotState.PAYMENT_QUANTITY,
        **current_context,
        booked_seat_count=booked_count,
        receipt_vk_message_url="",      # button flow - no receipt URL
        receipt_vk_message_ts=None,     # will use datetime.utcnow() in handler
    )
```

### Example 5: VKBottle Combined State + Func Handler Registration

```python
# Source: VKBottle source code - dispatch/handlers/from_func_handler.py
# AND dispatch/rules/base.py - StateRule + FuncRule both evaluated as AND conditions

# In payment.register_handlers(bot):
def register_handlers(bot: Bot):
    storage = bot.state_dispenser

    async def payment_quantity_with_storage(message: Message):
        await payment_quantity_handler(message, storage)

    # Handles button presses ([1], [2], ..., [Все N], [Отмена]) in PAYMENT_QUANTITY state
    bot.on.message(state=BotState.PAYMENT_QUANTITY)(payment_quantity_with_storage)

    logger.info("Payment handlers registered")
```

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| Phase 3 placeholder "Оплата" | Full payment flow | Implement now |
| `AWAITING_PAYMENT_AMOUNT` (commented in states.py) | `PAYMENT_QUANTITY` | Rename to match BOT_SPEC |

**Commented-out in states.py line 45:**
```python
# AWAITING_PAYMENT_AMOUNT = "awaiting_payment_amount"
```
Uncomment and rename to `PAYMENT_QUANTITY = "payment_quantity"` as the BOT_SPEC specifies.

---

## Open Questions

1. **Payment model NOT NULL fields for button flow**
   - What we know: `vk_message_url` and `vk_message_ts` are NOT NULL. Button flow has no receipt.
   - What's unclear: Whether to make fields nullable (schema change) or use empty/sentinel values.
   - Recommendation: Make fields nullable in Payment model + add Alembic migration. Create migration
     script as part of Phase 3. If no Alembic is set up yet, do a manual `ALTER TABLE` or recreate
     the DB for dev.

2. **VK Message URL format for receipts**
   - What we know: `fwd_messages[0]` has `.from_id` and `.id` (message ID). VK private message URLs
     use format `https://vk.com/im?sel={from_id}&msgid={msg_id}`.
   - What's unclear: Whether `fwd.id` is reliably the original message ID when forwarded.
   - Recommendation: Verify with a real forwarded message. If `fwd.id` is not available, use
     a fallback URL or leave as empty string with nullable field.

3. **`fwd_messages[0].date` availability**
   - What we know: VK API message objects have a `date` unix timestamp field.
   - What's unclear: Whether this field is populated on the forwarded message object in vkbottle-types.
   - Recommendation: Use `fwd.date if hasattr(fwd, 'date') and fwd.date else int(datetime.utcnow().timestamp())`.

4. **Alembic migration setup**
   - What we know: Project uses SQLAlchemy with `init_db()` in database.py. No Alembic seen in project files.
   - What's unclear: Whether Alembic is set up, or if schema is managed via `Base.metadata.create_all()`.
   - Recommendation: Check `database.py` - if using `create_all()`, just update the model and recreate.
     If production DB has data, use raw SQL ALTER TABLE.

---

## Sources

### Primary (HIGH confidence)
- Direct inspection of `/Users/thecattest/things/projects/Tickets/bot/` - all handler files read
- Direct inspection of `/Users/thecattest/things/projects/Tickets/models/` - all model files read
- VKBottle 4.6.2 source in `.venv/lib` - `dispatch/rules/base.py`, `dispatch/handlers/from_func_handler.py`,
  `framework/labeler/base.py` read directly

### Secondary (MEDIUM confidence)
- VKBottle labeler decorator pattern: `bot.on.message(state=X, func=Y)` confirmed by reading
  `base.py:get_custom_rules()` which maps both "state" and "func" as standard custom rules evaluated
  with AND logic via `FromFuncHandler.filter()`

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries verified from installed venv, all models read directly
- Architecture (handler dispatch): HIGH - VKBottle source read directly, rules are AND-ed
- Architecture (Payment model NOT NULL issue): HIGH - model file read directly, problem is definitive
- Architecture (forwarded message in MAIN_MENU): HIGH - current handler code read, behavior is clear
- Pitfalls: HIGH - derived from direct code reading, not speculation
- VK message URL format: LOW - not verified from VK API documentation directly

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (VKBottle 4.6.2 stable, SQLAlchemy stable)

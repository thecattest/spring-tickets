# Phase 3: Регистрация оплаты

**Status:** 🔜 PENDING
**Goal:** Полный цикл: бронь → оплата → детерминированный выбор мест
**Effort:** 12-15 hours

---

## Tasks

### 1. Payment via Forwarded Receipt

- [ ] Обработчик пересылки чека (detect by vk_message_url pattern):
  - Получить VK user ID автора чека
  - Проверить: есть ли активная бронь?
  - Ошибка: "У клиента {name} нет активной брони"
  - Получить BOOKED места (WHERE status='booked', released_at IS NULL)
  - Показать кнопки с количеством: [1] [2] ... [Все N]

- [ ] State: PAYMENT_QUANTITY

**Files to create/update:**
- `bot/handlers/payment.py` (new)

---

### 2. Deterministic Seat Selection

- [ ] Функция select_seats_for_payment(reservation_id, count):
  - SELECT ... WHERE status='booked' ORDER BY row_number ASC, seat_number ASC LIMIT N
  - Обновить status → PAID
  - Создать Payment запись (payment_amount, seat_count)
  - Создать PaymentSeat связи
  - Обновить Reservation.last_activity_at

- [ ] Обработка выбора количества:
  - Валидация: count <= available BOOKED seats
  - Ошибка: "Количество мест превышает доступные (N). Введите 1-N:"
  - Выполнить select_seats_for_payment
  - Показать подтверждение (какие места оплачены)
  - Показать остаток к оплате (если частичная)
  - Exit в IDLE

**Files to update:**
- `bot/utils/db.py` (new payment functions)

**DB function:**
```python
def record_payment(reservation_id, seat_count, vk_message_url, vk_message_ts, user_id):
    with db.begin():
        # Get seats deterministically
        seats = db.query(SeatAssignment).filter(
            SeatAssignment.reservation_id == reservation_id,
            SeatAssignment.status == SeatStatus.BOOKED,
            SeatAssignment.released_at.is_(None)
        ).order_by(
            SeatAssignment.row_number.asc(),
            SeatAssignment.seat_number.asc()
        ).limit(seat_count).all()

        if len(seats) < seat_count:
            raise InsufficientSeatsError(...)

        # Calculate amount
        amount = seat_count * SEAT_PRICE

        # Create Payment
        payment = Payment(...)
        db.add(payment)
        db.flush()

        # Update seats and create links
        for seat in seats:
            seat.status = SeatStatus.PAID
            ps = PaymentSeat(payment_id=payment.id, seat_assignment_id=seat.id)
            db.add(ps)

        # Update last_activity_at
        reservation.last_activity_at = datetime.utcnow()

        # Audit log
        audit = AuditLog(action_type="payment_recorded", ...)
        db.add(audit)

        db.commit()
        return payment
```

---

### 3. Payment via Menu Button

- [ ] Кнопка [Оплата] в главном меню:
  - Показать количество BOOKED мест
  - Кнопки: [1] [2] ... [Все N] [Отмена]
  - State: PAYMENT_QUANTITY (reuse)

---

### 4. Keyboards

- [ ] payment_quantity_keyboard(max_count) → [1] [2] ... [Все N] [Отмена]

**Files to update:**
- `bot/keyboards.py`

---

### 5. Configuration

- [ ] Add SEAT_PRICE to .env:
  ```env
  SEAT_PRICE=1500  # Цена одного места (руб)
  ```

- [ ] Load SEAT_PRICE in bot/config.py

---

### 6. Testing

- [ ] Test: payment via forwarded receipt
- [ ] Test: payment via menu button
- [ ] Test: deterministic seat selection (verify order)
- [ ] Test: partial payment (2 of 5 seats)
- [ ] Test: error when count > available
- [ ] Test: Payment record has correct amount and seat_count

---

## Success Criteria

- ✅ Можно зарегистрировать оплату по пересылке чека
- ✅ Можно зарегистрировать оплату через меню
- ✅ Детерминированный выбор мест работает (row ASC, seat ASC)
- ✅ Частичная оплата поддерживается
- ✅ Повторная оплата оставшихся мест работает
- ✅ Audit log фиксирует все платежи

---

## Dependencies

**Requires:**
- Phase 1, Phase 2 completed
- Payment.payment_amount, Payment.seat_count fields (added in Phase 0 ✅)
- SEAT_PRICE configured in .env

**Provides:**
- Payment recording
- Deterministic seat selection
- Financial tracking

**Blocks:**
- Phase 5 (debtors report - needs payments)

---

## Technical Notes

- Audit log: `payment_recorded` with payload {payment_id, seat_ids, amount, partial: bool}
- Payment amount calculation: seat_count * SEAT_PRICE
- Update Reservation.last_activity_at on every payment

---

## Next Phase

After Phase 3 completion:
- Phase 4: Reserve management (admin only)

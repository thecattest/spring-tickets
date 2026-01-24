# Phase 2: Главное меню и удаление мест

**Status:** 🔜 PENDING
**Goal:** Полноценная работа с бронью через главное меню
**Effort:** 10-12 hours

---

## Tasks

### 1. Main Menu Display

- [ ] Обработчик пересылки для existing reservation:
  - Проверить: есть ли активная бронь (reuse from Phase 1)
  - Если ДА: показать главное меню
  - Отобразить все места (сгруппированные по рядам)
  - Разбивка по статусам: BOOKED / PAID
  - Показать общее количество, к оплате
  - Кнопки: [Добавить] [Удалить] [Удалить все] [Оплата]

- [ ] FSM state: MAIN_MENU

**Files to update:**
- `bot/handlers/reservation.py`

---

### 2. Context Conflict Protection

- [ ] При пересылке проверить FSM state:
  - Если state != IDLE → показать ошибку
  - "Сейчас вы работаете с другим клиентом. Завершите операцию или /cancel"

**Error handling:**
- Prevent context switching mid-operation

---

### 3. Seat Deletion Flow

- [ ] Кнопка [Удалить] → State DELETING_ROW:
  - Запрос ряда
  - Валидация 1-24

- [ ] State DELETING_SEATS:
  - Запрос мест (seat_parser)
  - Валидация: места должны принадлежать брони
  - Валидация: status = BOOKED (не PAID)
  - Ошибка: "Места не найдены в брони или уже оплачены. Доступные: ..."
  - Обновление БД: released_at = NOW()
  - Обновление last_activity_at

- [ ] State DELETION_MENU:
  - Показать удаленные места
  - Показать остаток в брони
  - Кнопки: [Удалить еще] [Готово]

**Files to update:**
- `bot/handlers/reservation.py`

**DB operations:**
```python
def remove_seats_from_reservation(reservation_id, row, seats, user_id):
    # UPDATE seat_assignments
    # SET released_at = NOW(), released_by_user_id = user_id
    # WHERE reservation_id = X AND row_number = Y AND seat_number IN (...)
    #   AND status = 'booked' AND released_at IS NULL
```

---

### 4. Delete All (Cancel Reservation)

- [ ] Кнопка [Удалить все]:
  - Проверка прав: если есть PAID места И user != ADMIN → ошибка
  - Ошибка: "В брони есть оплаченные места (N шт.). Отменить может только админ."
  - Если admin ИЛИ нет PAID: показать подтверждение

- [ ] State CONFIRM_DELETE_ALL:
  - Подтверждение: [Подтверждаю] [Отмена]
  - Показать сколько мест будет удалено (BOOKED + PAID)

- [ ] Выполнение:
  - Освободить ВСЕ места (released_at = NOW())
  - Reservation.state = CANCELLED
  - Reservation.cancelled_at = NOW()
  - Audit log: reservation_cancelled

**Files to update:**
- `bot/handlers/reservation.py`
- `bot/utils/db.py` (check_user_role function)

**Admin check:**
```python
def is_admin(user_id: int) -> bool:
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    return user and user.role == UserRole.ADMIN
```

---

### 5. Updated Keyboards

- [ ] main_menu_keyboard() → [Добавить] [Удалить] [Удалить все] [Оплата]
- [ ] deletion_menu_keyboard() → [Удалить еще] [Готово]
- [ ] confirm_delete_all_keyboard() → [Подтверждаю] [Отмена]

**Files to update:**
- `bot/keyboards.py`

---

### 6. FSM States

- [ ] Добавить в bot/fsm/states.py:
  - MAIN_MENU
  - DELETING_ROW
  - DELETING_SEATS
  - DELETION_MENU
  - CONFIRM_DELETE_ALL

---

### 7. Testing

- [ ] Test: main menu display with mixed BOOKED/PAID seats
- [ ] Test: delete BOOKED seats successfully
- [ ] Test: attempt to delete PAID seats (should fail)
- [ ] Test: non-admin cannot delete all with PAID seats
- [ ] Test: admin can delete all with PAID seats
- [ ] Test: context conflict protection

---

## Success Criteria

- ✅ Пересылка от клиента с бронью открывает главное меню
- ✅ Можно добавлять места через меню (reuse Phase 1)
- ✅ Можно удалять места (только BOOKED)
- ✅ Можно отменить всю бронь
- ✅ Админ может отменить бронь с PAID местами
- ✅ Обычный пользователь не может отменить бронь с PAID
- ✅ Конфликт контекста обрабатывается корректно

---

## Dependencies

**Requires:**
- Phase 1 completed
- AppUser.role field (exists ✅)

**Provides:**
- Main menu navigation
- Seat deletion
- Reservation cancellation with role checks

**Blocks:**
- Phase 3 (payment registration)

---

## Technical Notes

- Audit log: `seat_removed`, `reservation_cancelled`
- Role check через AppUser.role == UserRole.ADMIN
- После удаления — остаться в DELETION_MENU (не exit)
- После отмены брони — exit в IDLE

---

## Next Phase

After Phase 2 completion:
- Phase 3: Payment registration and script generation

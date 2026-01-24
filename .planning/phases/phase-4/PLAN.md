# Phase 4: Управление резервами (Admin)

**Status:** 🔜 PENDING
**Goal:** Админы могут создавать/удалять резервы с обязательными комментариями
**Effort:** 8-10 hours

---

## Tasks

### 1. /reserve Command

- [ ] Обработчик /reserve:
  - Проверка role: AppUser.role == UserRole.ADMIN
  - Если не админ: "Управление резервами доступно только администраторам"
  - State: RESERVE_ACTION
  - Кнопки: [Добавить места] [Удалить места]

**Files to create:**
- `bot/handlers/reserve.py`

---

### 2. Add Reserve Flow

- [ ] State RESERVE_ACTION → [Добавить места]:
  - State: RESERVE_ADDING_ROW
  - Запрос ряда (1-24)

- [ ] State RESERVE_ADDING_SEATS:
  - Запрос мест (seat_parser)
  - Валидация: места не должны быть заняты

- [ ] State RESERVE_COMMENT:
  - Запрос комментария (обязательно!)
  - Валидация: комментарий не пустой
  - Создать SeatAssignment:
    - status = RESERVED
    - reservation_id = NULL
    - note = <комментарий>
  - Audit log: reserve_added
  - Подтверждение
  - Exit в IDLE

**DB function:**
```python
def add_reserve(row, seats, note, user_id):
    with db.begin():
        # Check availability
        for seat in seats:
            if not is_seat_available(row, seat):
                raise SeatConflictError(...)

        # Create assignments
        assignments = []
        for seat in seats:
            sa = SeatAssignment(
                row_number=row,
                seat_number=seat,
                status=SeatStatus.RESERVED,
                reservation_id=None,
                note=note,
                created_by_user_id=user_id
            )
            db.add(sa)
            assignments.append(sa)

        # Audit
        audit = AuditLog(action_type="reserve_added", ...)
        db.add(audit)

        db.commit()
```

---

### 3. Remove Reserve Flow

- [ ] State RESERVE_ACTION → [Удалить места]:
  - State: RESERVE_REMOVING_ROW
  - Запрос ряда

- [ ] State RESERVE_REMOVING_SEATS:
  - Запрос мест
  - Валидация: места должны быть в status=RESERVED
  - Ошибка: "Места не являются резервом"
  - Освободить: released_at = NOW()
  - Сохранить note в audit log payload
  - Подтверждение (показать предыдущий комментарий)
  - Exit в IDLE

---

### 4. Display Reserves in Conflict Errors

- [ ] Обновить seat conflict error message:
  - Если место RESERVED: показать комментарий
  - "Ряд X место Y (Резерв: {note})"

**Files to update:**
- `bot/utils/db.py` (is_seat_available improvements)

---

### 5. FSM States

- [ ] Add to bot/fsm/states.py:
  - RESERVE_ACTION
  - RESERVE_ADDING_ROW
  - RESERVE_ADDING_SEATS
  - RESERVE_COMMENT
  - RESERVE_REMOVING_ROW
  - RESERVE_REMOVING_SEATS

---

### 6. Keyboards

- [ ] reserve_action_keyboard() → [Добавить места] [Удалить места]

**Files to update:**
- `bot/keyboards.py`

---

### 7. Testing

- [ ] Test: non-admin cannot use /reserve
- [ ] Test: admin can add reserve with comment
- [ ] Test: reserve comment is mandatory
- [ ] Test: admin can remove reserve
- [ ] Test: reserve conflicts shown in error messages
- [ ] Test: audit log has reserve actions

---

## Success Criteria

- ✅ Админы могут использовать /reserve
- ✅ Не-админы не могут использовать /reserve
- ✅ Можно создать резерв с обязательным комментарием
- ✅ Можно удалить резерв
- ✅ Резервы отображаются при проверке занятости
- ✅ Комментарий сохраняется в SeatAssignment.note
- ✅ При удалении комментарий логируется

---

## Dependencies

**Requires:**
- Phase 1-3 completed
- AppUser.role field (exists ✅)

**Provides:**
- Reserve management for admins
- Comments for reserved seats

**Blocks:**
- None (independent feature)

---

## Technical Notes

- Резервы НЕ привязаны к Reservation (reservation_id=NULL)
- Комментарий ОБЯЗАТЕЛЕН для резервов
- Audit log: `reserve_added`, `reserve_removed` with note in payload

---

## Next Phase

After Phase 4 completion:
- Phase 5: Debtors report and automatic reminders

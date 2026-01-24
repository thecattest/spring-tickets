# Phase 5: Должники и автоматические напоминания

**Status:** 🔜 PENDING
**Goal:** Билетеры видят список должников, автоматические напоминания работают
**Effort:** 6-8 hours

---

## Tasks

### 1. /debtors Command

- [ ] Обработчик /debtors:
  - Получить user_id билетера
  - Проверить роль: админ видит всех, билетер — только своих
  - Запрос к БД (debtors query)
  - Отобразить список должников
  - Кнопки: [Обновить] [Закрыть]

**Debtors query:**
```sql
SELECT r.*, vk.display_name, COUNT(sa.id) as seat_count
FROM reservations r
JOIN vk_users vk ON r.buyer_vk_user_id = vk.id
LEFT JOIN seat_assignments sa ON sa.reservation_id = r.id
  AND sa.released_at IS NULL
  AND sa.status = 'booked'
WHERE r.state = 'active'
  AND r.last_activity_at <= NOW() - INTERVAL '7 days'
  AND (r.sold_by_user_id = <user_id> OR <is_admin>)
GROUP BY r.id, vk.id
ORDER BY r.last_activity_at ASC
```

**Files to create:**
- `bot/handlers/debtors.py`

**Message format:**
```
Должники (не было оплат >= 7 дней):

1. [Имя Фамилия]
   Бронь от {date}, мест: {count} (все не оплачено)
   Последняя активность: {date}

2. [Имя Фамилия]
   ...

Всего: {N} должников, {M} неоплаченных мест

[Обновить] [Закрыть]
```

---

### 2. Refresh Button

- [ ] Кнопка [Обновить]:
  - Повторить запрос
  - Обновить сообщение
  - Показать timestamp обновления

---

### 3. Cron Script

- [ ] Создать scripts/send_debtors_reminders.py:
  - Подключение к БД
  - Выполнение debtors query
  - Группировка должников по билетерам
  - Отправка сообщений через VK Bot API
  - Audit log для каждой рассылки

**Script structure:**
```python
#!/usr/bin/env python3
from database import get_session
from models import Reservation, VkUser, AppUser, AuditLog
from bot.config import VK_BOT_TOKEN

def get_debtors_by_seller():
    # Query debtors grouped by sold_by_user_id
    ...

def send_reminder(seller_id, debtors):
    # Format message
    # Send via VK API to seller's VK ID
    # Log audit
    ...

if __name__ == "__main__":
    session = get_session()
    debtors_map = get_debtors_by_seller()
    for seller_id, debtors in debtors_map.items():
        send_reminder(seller_id, debtors)
```

**Files to create:**
- `scripts/send_debtors_reminders.py`

---

### 4. Cron Configuration

- [ ] Add to crontab:
  ```
  0 20 */3 * * cd /path/to/project && /path/to/python3 scripts/send_debtors_reminders.py >> logs/cron_reminders.log 2>&1
  ```

- [ ] Document in README.md:
  - How to configure cron
  - How to change time/frequency
  - Where logs are stored

---

### 5. Configuration

- [ ] Add to .env:
  ```env
  DEBTORS_DAYS_THRESHOLD=7
  DEBTORS_REMINDER_TIME=20:00  # Moscow time (optional - документация)
  ```

- [ ] Load in bot/config.py

---

### 6. Keyboards

- [ ] debtors_keyboard() → [Обновить] [Закрыть]

**Files to update:**
- `bot/keyboards.py`

---

### 7. Testing

- [ ] Test: /debtors shows correct debtors for seller
- [ ] Test: /debtors shows all debtors for admin
- [ ] Test: [Обновить] refreshes list
- [ ] Test: cron script generates correct messages
- [ ] Test: audit log records debtors_notification_sent

---

## Success Criteria

- ✅ Команда /debtors работает корректно
- ✅ Каждый билетер видит только своих должников
- ✅ Админы видят всех должников
- ✅ Cron скрипт отправляет напоминания
- ✅ Напоминания логируются в audit log
- ✅ Threshold (7 дней) конфигурируется

---

## Dependencies

**Requires:**
- Phase 1-3 completed (need payments to identify debtors)
- Cron access on server
- VK Bot API for sending messages outside webhook

**Provides:**
- Debtors tracking
- Automatic reminders

**Blocks:**
- None (independent feature)

---

## Technical Notes

- Audit log: `debtors_notification_sent` with payload {billeteer_id, debtor_count, total_seats}
- Threshold: 7 days since last_activity_at
- Frequency: every 3 days (configurable via cron)
- Time: TBD by user (configured in crontab)

---

## Optional Optimization

If Phase 5 implementation reveals slow debtors query:
- Add composite index: `CREATE INDEX reservations_debtors_idx ON reservations(sold_by_user_id, last_activity_at) WHERE state='active'`
- See DB_VALIDATION.md section 1.6

---

## Next Phase

After Phase 5 completion:
- Phase 6: Statistics and polish (final phase)

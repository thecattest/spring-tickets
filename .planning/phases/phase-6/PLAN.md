# Phase 6: Статистика и полировка

**Status:** 🔜 PENDING
**Goal:** Дополнительные функции для удобства + финальная доработка
**Effort:** 10-12 hours

---

## Tasks

### 1. /mystats Command (Seller)

- [ ] Обработчик /mystats:
  - Количество броней (активные/отмененные)
  - Количество оплаченных мест
  - Общая сумма продаж
  - За текущий месяц + за все время
  - Кнопка [Обновить]

**Stats queries:**
```sql
-- Active reservations
SELECT COUNT(*) FROM reservations WHERE sold_by_user_id = X AND state = 'active'

-- Cancelled reservations
SELECT COUNT(*) FROM reservations WHERE sold_by_user_id = X AND state = 'cancelled'

-- Paid seats (current month)
SELECT COUNT(ps.seat_assignment_id)
FROM payments p
JOIN payment_seats ps ON ps.payment_id = p.id
WHERE p.recorded_by_user_id = X
  AND p.recorded_at >= date_trunc('month', NOW())

-- Total revenue (current month)
SELECT SUM(p.payment_amount)
FROM payments p
WHERE p.recorded_by_user_id = X
  AND p.recorded_at >= date_trunc('month', NOW())
```

**Files to create:**
- `bot/handlers/stats.py`

**Message format:**
```
Ваша статистика:

Текущий месяц:
• Брони: {N} активных
• Оплачено мест: {M}
• Сумма: {X} руб.

За все время:
• Брони: {total_active} активных, {total_cancelled} отменено
• Оплачено мест: {total_seats}
• Сумма: {total_revenue} руб.

[Обновить]
```

---

### 2. Admin Statistics

- [ ] Команда /adminstats (admin only):
  - Общая статистика по всем билетерам
  - Топ-продавцов (по количеству мест / по сумме)
  - Процент оплаты (оплачено / забронировано)
  - Breakdown по месяцам

**Top sellers query:**
```sql
-- By seats
SELECT u.display_name, COUNT(ps.seat_assignment_id) as seat_count
FROM app_users u
JOIN payments p ON p.recorded_by_user_id = u.id
JOIN payment_seats ps ON ps.payment_id = p.id
GROUP BY u.id
ORDER BY seat_count DESC
LIMIT 10

-- By revenue
SELECT u.display_name, SUM(p.payment_amount) as revenue
FROM app_users u
JOIN payments p ON p.recorded_by_user_id = u.id
GROUP BY u.id
ORDER BY revenue DESC
LIMIT 10
```

---

### 3. Improved Error Messages

- [ ] Review all error messages:
  - Add examples to each error
  - More detailed explanations
  - Consistent formatting

**Example updates:**
```
Before: "Неверный формат"
After: "Неверный формат. Введите номера мест через пробел, запятые или диапазон.
Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
```

---

### 4. Logging Setup

- [ ] Configure logging in bot/config.py:
  - Levels: DEBUG, INFO, WARNING, ERROR
  - RotatingFileHandler (10MB per file, keep 5 files)
  - Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
  - Separate files: bot.log, errors.log

- [ ] Log all FSM transitions (INFO level)
- [ ] Log all DB operations (DEBUG level)
- [ ] Log all errors with stack traces (ERROR level)

**Files to update:**
- `bot/config.py`

---

### 5. Redis Monitoring

- [ ] Add Redis health check in bot/main.py:
  - Check connection on startup
  - Auto-reconnect on connection loss
  - Log connection status

**Files to update:**
- `bot/main.py`

---

### 6. Testing

- [ ] Unit tests:
  - seat_parser edge cases
  - layout loading
  - db functions isolation

- [ ] Integration tests:
  - Full reservation flow (create → add → pay)
  - Concurrent seat booking (2 threads, same seat)
  - Admin vs seller permissions

- [ ] Load testing:
  - 10 concurrent users
  - 100 rapid seat additions
  - Measure response times

**Files to create:**
- `bot/tests/test_unit.py`
- `bot/tests/test_integration.py`
- `bot/tests/test_load.py`

**Tools:**
- pytest for unit/integration
- pytest-asyncio for async handlers
- pytest-xdist for parallel tests

---

### 7. Documentation

- [ ] README.md:
  - Installation instructions
  - Configuration guide (.env)
  - Running the bot
  - Running tests
  - Deployment notes

- [ ] BILLETEER_GUIDE.md:
  - How to use the bot (for sellers)
  - All commands explained
  - Examples with screenshots (if possible)
  - Troubleshooting common issues

- [ ] ADMIN_GUIDE.md:
  - Additional admin commands
  - Reserve management
  - Statistics interpretation
  - Cron configuration

**Files to create:**
- `README.md`
- `docs/BILLETEER_GUIDE.md`
- `docs/ADMIN_GUIDE.md`

---

### 8. Code Quality

- [ ] Add type hints to all functions
- [ ] Add docstrings to all modules/classes/functions
- [ ] Run linter (pylint or flake8)
- [ ] Fix all linter warnings
- [ ] Code review checklist

---

### 9. Performance Monitoring

- [ ] Add response time logging:
  - Log time for each handler execution
  - Log time for each DB query
  - Weekly summary of average response times

- [ ] Add metrics:
  - Messages processed per day
  - Reservations created per day
  - Payments recorded per day
  - Error rate

---

## Success Criteria

- ✅ Статистика работает корректно
- ✅ Логи записываются и ротируются
- ✅ Тесты покрывают основные сценарии (>70% coverage)
- ✅ Документация актуальна и понятна
- ✅ Бот стабильно работает под нагрузкой (10 параллельных пользователей)
- ✅ Все ошибки обрабатываются gracefully
- ✅ Response time <2 секунды для всех операций

---

## Dependencies

**Requires:**
- Phase 1-5 completed

**Provides:**
- Production-ready bot
- Complete documentation
- Monitoring and metrics
- Performance validation

**Blocks:**
- None (final phase)

---

## Technical Notes

- Test coverage target: >70%
- Response time target: <2 seconds
- Log rotation: 10MB per file, keep 5 files
- Load test: 10 concurrent users without errors

---

## Deployment Checklist

After Phase 6 completion:

- [ ] All tests passing
- [ ] Documentation complete
- [ ] .env configured on production server
- [ ] Redis running and accessible
- [ ] Database initialized
- [ ] Cron configured for debtors reminders
- [ ] VK Bot API token valid
- [ ] Bot running as systemd service (or equivalent)
- [ ] Logs directory writable
- [ ] Monitoring enabled
- [ ] Backup strategy in place

---

## Next Steps

After Phase 6:
- Production deployment
- User training (billeteer guide)
- Monitor for issues
- Iterate based on feedback

---

**Project Complete!** 🎉

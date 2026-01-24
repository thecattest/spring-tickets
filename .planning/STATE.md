# Project State

**Last updated:** 2026-01-24
**Current phase:** Planning complete, ready for Phase 1 execution

---

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-01-24)

**Core value:** Ни одно место не может быть продано дважды
**Current focus:** Подготовка к разработке Phase 1 (Основа бота и создание броней)

---

## Current Status

### Completed

✅ **Infrastructure & Database Layer**
- SQLAlchemy models для всех сущностей (VKUser, AppUser, Reservation, SeatAssignment, Payment, AuditLog)
- Partial index для уникальности занятости мест
- Тесты базы данных (test_db.py)
- Миграция SQLite → PostgreSQL задокументирована

✅ **Planning & Documentation**
- Детальная спецификация бота (`.planning/BOT_SPEC.md`) — 1200 строк
- Все сценарии документированы с FSM states
- Обработка ошибок описана
- Структура проекта определена
- Codebase mapping complete (`.planning/codebase/`)

✅ **Technical Decisions**
- VKBottle выбран для VK Bot API
- Redis для FSM permanent storage
- Детерминированная частичная оплата (row ASC, seat ASC)
- Формат ввода мест: пробелы/запятые/диапазоны

### In Progress

🔄 **Phase 1 Preparation**
- Roadmap создан с 6 фазами
- PROJECT.md инициализирован
- Готовность к началу разработки

### Blocked

❌ **Требуют уточнения перед началом разработки:**
1. AppUser.is_admin — существует ли поле в модели? (нужно для Phase 2, 4)
2. Время отправки напоминаний должникам (для cron в Phase 5)
3. SEAT_PRICE — цена одного места (для расчета сумм в Phase 3)

---

## Next Steps

### Immediate (перед началом Phase 1)

1. **Проверить модель AppUser:**
   - Есть ли поле `is_admin`?
   - Если нет — добавить в миграцию

2. **Создать .env.example:**
   - VK_BOT_TOKEN
   - VK_GROUP_ID
   - REDIS_HOST/PORT/DB
   - DATABASE_URL
   - SEAT_PRICE
   - DEBTORS_DAYS_THRESHOLD=7

3. **Создать layout.json:**
   - Структура зала (24 ряда × 28 мест)
   - Формат JSON для валидации

### Phase 1 Execution

После уточнений выше:

1. Инициализация VKBottle проекта
2. Подключение Redis FSM storage
3. Реализация базовых команд (/start, /help, /cancel)
4. Сценарий создания брони
5. Парсер мест с поддержкой всех форматов
6. Генерация скрипта

**Estimated:** 15-20 hours

---

## Open Questions

1. **AppUser модель:**
   - Есть ли поле is_admin?
   - Как определять роль пользователя?

2. **Payment reversal (из CONCERNS.md):**
   - Использовать отдельную таблицу payment_reversals?
   - Или хранить в audit log?
   - Какая модель лучше для финансовой отчетности?

3. **Audit log action types:**
   - Каталог финализирован в BOT_SPEC.md
   - Нужно ли добавлять дополнительные типы?

4. **Скрипт для клиента:**
   - Текущий шаблон универсален?
   - Нужны ли вариации для разных ситуаций (бронь/частичная оплата/полная оплата)?

5. **Время напоминаний должникам:**
   - Какое время отправки? (например: 20:00 МСК)
   - Timezone handling?

---

## Metrics

### Codebase
- **Models:** 7 файлов (base, user, vk_user, reservation, seat_assignment, payment, audit)
- **Tests:** 1 файл (test_db.py) — базовые сценарии покрыты
- **Documentation:** 4 файла (BOT_SPEC.md, PROJECT.md, ROADMAP.md, CONCERNS.md)
- **Total lines:** ~2500 (models + tests + docs)

### Planning
- **Phases defined:** 6
- **Total estimated effort:** 61-77 hours
- **MVP estimated effort:** 37-47 hours (Phases 1-3)
- **Requirements:** 6 validated, 24 active, 5 out of scope

### Progress
- **Database layer:** 100% complete
- **Bot development:** 0% (not started)
- **Planning:** 100% complete
- **Overall project:** ~25% (infrastructure готов, основная разработка впереди)

---

## Recent Activity

**2026-01-24:**
- Запущен `/gsd:map-codebase` — создано 7 документов о кодовой базе
- Обсуждение деталей реализации VK бота
- Созданы BOT_SPEC.md (1200 строк), PROJECT.md, ROADMAP.md
- Технические решения:
  - Формат ввода мест: пробелы/запятые/диапазоны
  - Скрипт после брони, не после оплаты
  - Резервы — отдельная команда, не привязаны к брони
  - Админ-only удаление броней с оплаченными местами
  - Redis permanent storage (no TTL)

---

## Dependencies Status

### External Services
- ✅ SQLite — используется для MVP
- ⏳ PostgreSQL — миграция запланирована при масштабировании
- ⏳ Redis — нужно установить и настроить для Phase 1
- ⏳ VK Bot API — нужен токен для разработки

### Python Packages
- ✅ SQLAlchemy 2.0+ — установлен
- ⏳ vkbottle — установить в Phase 1
- ⏳ redis-py — установить в Phase 1
- ⏳ python-dotenv — установить в Phase 1

---

*State tracking active since: 2026-01-24*

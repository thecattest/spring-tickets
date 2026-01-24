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

🔄 **Phase 0: Валидация архитектуры БД**
- Проверка покрытия всех ботовых сценариев
- Проверка индексов для критичных запросов
- Выявление недостающих полей/связей
- Проверка audit log action types

🔄 **Phase 1 Preparation**
- Roadmap создан с 7 фазами (Phase 0 + 6 основных)
- PROJECT.md инициализирован
- layout.json создан

### Blocked

❌ **Требуют уточнения перед началом разработки:**
1. ✅ ~~AppUser.is_admin~~ — решено: используется `AppUser.role == UserRole.ADMIN`
2. ✅ ~~layout.json структура~~ — создан с переменным количеством мест (21-28) в 24 рядах
3. Время отправки напоминаний должникам (для cron в Phase 5)
4. SEAT_PRICE — цена одного места (для расчета сумм в Phase 3)

---

## Next Steps

### Immediate (Phase 0)

**Валидация архитектуры БД (~2-3 hours):**

1. **Проверить покрытие сценариев:**
   - Создание брони, добавление/удаление мест
   - Регистрация оплаты (детерминированная выборка)
   - Управление резервами (с комментариями)
   - Поиск должников

2. **Проверить индексы:**
   - Поиск активной брони по buyer_vk_user_id
   - Поиск мест по reservation_id
   - Проверка занятости (row, seat, released_at IS NULL)
   - Должники по sold_by_user_id + last_activity_at

3. **Проверить недостающие элементы:**
   - Поля для связи билетера с VK (AppUser.vk_user_id)
   - Audit log action types из BOT_SPEC.md
   - Constraints согласованы с layout.json?

4. **Создать DB_VALIDATION.md:**
   - Результаты проверки
   - Список изменений (если требуется)
   - Обновить CONCERNS.md

### Before Phase 1

1. **Создать .env.example:**
   - VK_BOT_TOKEN, VK_GROUP_ID
   - REDIS_HOST/PORT/DB
   - DATABASE_URL
   - SEAT_PRICE (требует уточнения)
   - DEBTORS_DAYS_THRESHOLD=7

2. **Уточнить открытые вопросы:**
   - SEAT_PRICE — цена одного места
   - Время отправки напоминаний должникам

### Phase 1 Execution

После Phase 0 и уточнений:

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

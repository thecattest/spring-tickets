# Project Milestones: Система продажи билетов через VK бота

## v0.2 — Рефакторинг архитектуры бота (Shipped: 2026-02-20)

**Delivered:** Полная перестройка архитектуры бота — централизованный роутер, декларативный FSM конфиг, переиспользуемые шаги, единые источники правды для UI-строк, интуитивная навигация.

**Phases completed:** 7-12 (20 plans total)

**Key accomplishments:**

- Центральный роутер заменил 7 register_handlers() и 14 closure-обёрток с автоматической инъекцией storage и проверкой auth guard
- Декларативный FSM_CONFIG (18 состояний) + 3 переиспользуемых шага заменили ~335 строк дублированного кода
- bot/constants.py (Btn/Cmd StrEnum) + bot/texts.py (62+ констант) — единый источник правды для всех UI-строк
- /cancel → возврат на один шаг назад через FSM_CONFIG.back_state, /exit → полный сброс в IDLE
- Ранняя валидация ряда в 4 хендлерах — предотвращает бесполезный ввод мест
- Все 7 файлов хендлеров мигрированы атомарно, zero regressions

**Stats:** 76 files modified, 5,997 LOC Python, 6 phases, 20 plans, 2 days
**Git range:** `fix(07-01)` → `test(12)`
**Archive:** milestones/v0.2-ROADMAP.md, milestones/v0.2-REQUIREMENTS.md

---

## v0.1 — VK Bot MVP (Shipped: 2026-02-18)

**Delivered:** Минимально жизнеспособный бот для продажи билетов — создание броней, управление местами, регистрация оплаты, резервы, должники, веб-карта зала.

**Phases completed:** 0-5 (13 plans total)

**Key accomplishments:**

- Database layer with atomic seat occupancy (SeatAssignment partial index)
- VK bot with full reservation lifecycle: create → add seats → pay → cancel
- Admin reserve management (/reserve)
- Debtors tracking (/debtors) + cron reminders
- Web hall map + payments dashboard

**Stats:** 6 phases (0-5), 13 plans executed, ~25 days
**Archive:** milestones/v0.1-ROADMAP.md (if exists)

---

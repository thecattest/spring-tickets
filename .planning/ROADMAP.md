# Roadmap: VK бот для продажи билетов

## Milestones

- ✅ **v0.1 MVP** — Phases 0-5 (complete 2026-02-18)
- 🚧 **v0.2 Рефакторинг архитектуры бота** — Phases 7-12 (in progress)
- 📋 **v0.3 Статистика** — Phase 6 deferred (planned post-refactoring)

## Phases

<details>
<summary>✅ v0.1 VK Bot MVP (Phases 0-5) — COMPLETE 2026-02-18</summary>

### Phase 0: Валидация архитектуры БД
**Goal:** Убедиться, что архитектура БД покрывает все сценарии бота.
**Status:** Complete

### Phase 1: Основа бота и создание броней
**Goal:** Минимальный рабочий бот для создания броней и добавления мест.
**Status:** Complete (2026-01-24)

### Phase 2: Главное меню и удаление мест
**Goal:** Полноценная работа с бронью через главное меню.
**Status:** Complete (2026-01-24)

Plans:
- [x] 02-01-PLAN.md — FSM states, formatting utilities, keyboards
- [x] 02-02-PLAN.md — Main menu display, context switching
- [x] 02-03-PLAN.md — Seat deletion and reservation cancellation
- [x] 02-04-PLAN.md — Gap closure: Fix same-client detection bug

### Phase 3: Регистрация оплаты
**Goal:** Полный цикл: бронь → оплата → скрипт для клиента.
**Status:** Complete (2026-02-18)

Plans:
- [x] 03-01-PLAN.md — Payment foundation
- [x] 03-02-PLAN.md — Payment handlers
- [x] 03-03-PLAN.md — Gap closure: Fix receipt forwarding

### Phase 4: Управление резервами (админ)
**Goal:** Админы могут создавать/удалять резервы с комментариями.
**Status:** Complete (2026-02-18)

Plans:
- [x] 04-01-PLAN.md — Reserve foundation
- [x] 04-02-PLAN.md — Reserve handler

### Phase 5: Просмотр должников и напоминания
**Goal:** Билетеры видят список должников, автоматические напоминания работают.
**Status:** Complete (2026-02-18)

Plans:
- [x] 05-01-PLAN.md — /debtors command
- [x] 05-02-PLAN.md — Cron reminder script

</details>

---

### 🚧 v0.2 Рефакторинг архитектуры бота (In Progress)

**Milestone Goal:** Устранить ~335+ строк дублированного кода в хендлерах, создать переиспользуемые абстракции (constants, router, steps, texts), улучшить UX навигации.

- [ ] **Phase 7: Bug Fix** — Исправить контекстный баг восстановления состояния
- [ ] **Phase 8: Foundation** — Создать constants.py, texts.py, обновить keyboards.py
- [ ] **Phase 9: FSM Config + Steps** — Декларативный конфиг FSM и переиспользуемые примитивы шагов
- [ ] **Phase 10: Router** — Центральный реестр хендлеров с универсальным перехватом команд
- [ ] **Phase 11: Handler Migration** — Миграция всех 7 файлов хендлеров на router + steps
- [ ] **Phase 12: Navigation UX** — /cancel → назад, /exit → IDLE, ранняя валидация ряда

---

## Phase Details

### Phase 7: Bug Fix

**Goal:** Устранить производственный баг: после нажатия "Нет" в context_switch_handler пользователь застревает в некорректном состоянии.
**Depends on:** Nothing (first phase of v0.2)
**Requirements:** BUG-01
**Success Criteria** (what must be TRUE):
  1. Билетер нажимает "Нет" в диалоге смены контекста — бот возвращает его в то состояние, в котором он был до пересылки
  2. Все 16 FSM-состояний корректно восстанавливаются через `BotState(original_state)` без KeyError
**Plans:** TBD

Plans:
- [ ] 07-01: Fix BotState enum restoration in context_switch_handler (menu.py:325)

---

### Phase 8: Foundation

**Goal:** Единый источник правды для всех UI-строк: кнопки, команды и пользовательские сообщения вынесены в отдельные модули, keyboards.py не содержит raw strings.
**Depends on:** Phase 7
**Requirements:** CONST-01, CONST-02, TEXT-01
**Success Criteria** (what must be TRUE):
  1. Все строки кнопок в keyboards.py читаются из `Btn.*` — ни одного строкового литерала для кнопок
  2. Все пользовательские сообщения (промпты, ошибки) содержатся в bot/texts.py с .format() плейсхолдерами
  3. `Btn`, `Cmd`, `ALL_COMMANDS` импортируются из bot/constants.py и работают как обычные строки в vkbottle параметрах
**Plans:** TBD

Plans:
- [ ] 08-01: Create bot/constants.py (Btn, Cmd StrEnums, ALL_COMMANDS frozenset)
- [ ] 08-02: Create bot/texts.py (all user-facing strings consolidated)
- [ ] 08-03: Update bot/keyboards.py to use Btn.* instead of raw string literals

---

### Phase 9: FSM Config + Steps

**Goal:** Декларативный конфиг FSM описывает все 16 состояний единым источником правды; три переиспользуемых примитива шагов заменяют 4+4+3 дублированных блока.
**Depends on:** Phase 8
**Requirements:** FSM-01, STEP-01, STEP-02, STEP-03
**Success Criteria** (what must be TRUE):
  1. Конфиг FSM описывает для каждого состояния: handler, input type, validators, auth guard, forward transitions, back state — всё в одном месте
  2. `handle_row_input()` вызывается из reservation, deletion, reserve flows и возвращает типизированный `RowResult` без дублирования логики валидации
  3. `handle_seat_input()` принимает строку ввода мест, валидирует по layout и availability, возвращает `SeatResult`
  4. `handle_confirmation()` обрабатывает yes/no ввод и возвращает `Optional[bool]` — один код для всех подтверждений
**Plans:** TBD

Plans:
- [ ] 09-01: Create FSM config (declarative per-state definitions in bot/fsm/ or bot/router.py)
- [ ] 09-02: Create bot/steps.py with handle_row_input(), handle_seat_input(), handle_confirmation()

---

### Phase 10: Router

**Goal:** Центральный роутер заменяет 7 функций register_handlers() и 14 closure-обёрток; команды перехватываются из любого FSM-состояния.
**Depends on:** Phase 9
**Requirements:** RTR-01, RTR-02, RTR-03
**Success Criteria** (what must be TRUE):
  1. Команды `/start`, `/help`, `/cancel`, `/exit` работают из любого из 16 FSM-состояний — не только из MAIN_MENU и RESERVE_ACTION
  2. Router читает FSM config и автоматически регистрирует хендлеры с инъекцией storage и проверкой auth guard
  3. `register_all()` гарантирует порядок: forwarded-message handler первый, затем command handlers, затем state handlers
  4. bot/main.py использует `bot.labeler.load(router.labeler)` вместо цепочки register_handlers() вызовов
**Plans:** TBD

Plans:
- [ ] 10-01: Create bot/router.py (Router class, decorators, register_all() with enforced ordering)
- [ ] 10-02: Wire router into bot/main.py, verify universal command interception

---

### Phase 11: Handler Migration

**Goal:** Все 7 файлов хендлеров используют @router декораторы и shared steps; все register_handlers() функции и closure-обёртки удалены.
**Depends on:** Phase 10
**Requirements:** MIG-01, MIG-02, MIG-03, MIG-04, MIG-05, MIG-06, MIG-07, MIG-08, MIG-09
**Success Criteria** (what must be TRUE):
  1. Все существующие боты-флоу (создание брони, удаление, оплата, резервы, должники) работают идентично — ни один сценарий не сломан
  2. В кодовой базе нет ни одной функции `register_handlers()` и ни одной closure-обёртки для инъекции storage
  3. bot/main.py содержит только импорты модулей хендлеров (для срабатывания декораторов) и один вызов `bot.labeler.load(router.labeler)`
  4. Каждый файл хендлера мигрирован атомарно: в одном коммите новые декораторы + удаление старой регистрации + обновление main.py
**Plans:** TBD

Plans:
- [ ] 11-01: Migrate bot/handlers/reservation.py (atomic commit)
- [ ] 11-02: Migrate bot/handlers/deletion.py (atomic commit)
- [ ] 11-03: Migrate bot/handlers/reserve.py (atomic commit)
- [ ] 11-04: Migrate bot/handlers/commands.py (atomic commit)
- [ ] 11-05: Migrate bot/handlers/menu.py — remove command dispatch elif block (atomic commit)
- [ ] 11-06: Migrate bot/handlers/payment.py (atomic commit)
- [ ] 11-07: Migrate bot/handlers/debtors.py — read file first, verify "Обновить" handling (atomic commit)
- [ ] 11-08: Remove all register_handlers() and closure wrappers, update main.py

---

### Phase 12: Navigation UX

**Goal:** Билетеры получают интуитивную навигацию: /cancel возвращает на предыдущий шаг, /exit сбрасывает в IDLE, ранняя валидация ряда предотвращает бесполезный ввод мест.
**Depends on:** Phase 11
**Requirements:** NAV-01, NAV-02, NAV-03
**Success Criteria** (what must be TRUE):
  1. Билетер в середине операции (например, вводит номера мест) нажимает /cancel — бот возвращает его к предыдущему шагу (ввод ряда), а не в IDLE
  2. Билетер нажимает /exit из любого состояния — FSM сбрасывается в IDLE с подтверждающим сообщением
  3. Билетер вводит ряд без доступных мест для текущей операции — бот сразу сообщает об этом и не запрашивает номера мест
  4. Весь BACK_MAP для всех 16 состояний определён до начала реализации — нет состояний с неопределённым поведением /cancel
**Plans:** TBD

Plans:
- [ ] 12-01: Define complete BACK_MAP covering all 16 states; implement NAV-01 (/cancel → back state)
- [ ] 12-02: Implement NAV-02 (/exit → IDLE) and NAV-03 (early row validation)

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 0. Валидация БД | v0.1 | — | Complete | 2026-01-24 |
| 1. Основа бота | v0.1 | 1/1 | Complete | 2026-01-24 |
| 2. Меню и удаление | v0.1 | 4/4 | Complete | 2026-01-24 |
| 3. Оплата | v0.1 | 3/3 | Complete | 2026-02-18 |
| 4. Резервы | v0.1 | 2/2 | Complete | 2026-02-18 |
| 5. Должники | v0.1 | 2/2 | Complete | 2026-02-18 |
| 6. Статистика | v0.1 | — | Deferred | — |
| 7. Bug Fix | v0.2 | 0/1 | Not started | — |
| 8. Foundation | v0.2 | 0/3 | Not started | — |
| 9. FSM Config + Steps | v0.2 | 0/2 | Not started | — |
| 10. Router | v0.2 | 0/2 | Not started | — |
| 11. Handler Migration | v0.2 | 0/8 | Not started | — |
| 12. Navigation UX | v0.2 | 0/2 | Not started | — |

---

*Roadmap updated: 2026-02-19 — v0.2 phases 7-12 added*

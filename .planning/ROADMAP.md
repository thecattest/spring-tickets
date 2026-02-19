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

- [x] **Phase 7: Bug Fix** — Исправить контекстный баг восстановления состояния
- [x] **Phase 8: Foundation** — Создать constants.py, texts.py, обновить keyboards.py
- [x] **Phase 9: FSM Config + Steps** — Декларативный конфиг FSM и переиспользуемые примитивы шагов
- [x] **Phase 10: Router** — Центральный реестр хендлеров с универсальным перехватом команд
- [x] **Phase 11: Handler Migration** — Миграция всех 7 файлов хендлеров на router + steps
- [x] **Phase 12: Navigation UX** — /cancel → назад, /exit → IDLE, ранняя валидация ряда

---

## Phase Details

### Phase 7: Bug Fix

**Goal:** Устранить производственный баг: после нажатия "Нет" в context_switch_handler пользователь застревает в некорректном состоянии.
**Depends on:** Nothing (first phase of v0.2)
**Requirements:** BUG-01
**Success Criteria** (what must be TRUE):
  1. Билетер нажимает "Нет" в диалоге смены контекста — бот возвращает его в то состояние, в котором он был до пересылки
  2. Все 16 FSM-состояний корректно восстанавливаются через `BotState(original_state)` без KeyError
**Plans:** 1 plan

Plans:
- [x] 07-01-PLAN.md — Fix BotState enum restoration in context_switch_handler (menu.py:325)

---

### Phase 8: Foundation

**Goal:** Единый источник правды для всех UI-строк: кнопки, команды и пользовательские сообщения вынесены в отдельные модули, keyboards.py не содержит raw strings.
**Depends on:** Phase 7
**Requirements:** CONST-01, CONST-02, TEXT-01
**Success Criteria** (what must be TRUE):
  1. Все строки кнопок в keyboards.py читаются из `Btn.*` — ни одного строкового литерала для кнопок
  2. Все пользовательские сообщения (промпты, ошибки) содержатся в bot/texts.py с .format() плейсхолдерами
  3. `Btn`, `Cmd`, `ALL_COMMANDS` импортируются из bot/constants.py и работают как обычные строки в vkbottle параметрах
**Status:** Complete (2026-02-19)
**Plans:** 3 plans

Plans:
- [x] 08-01-PLAN.md — Create bot/constants.py (Btn, Cmd StrEnums, ALL_COMMANDS frozenset)
- [x] 08-02-PLAN.md — Create bot/texts.py (all user-facing strings consolidated)
- [x] 08-03-PLAN.md — Update bot/keyboards.py to use Btn.* instead of raw string literals

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
**Plans:** 2 plans

**Status:** Complete (2026-02-19)

Plans:
- [x] 09-01-PLAN.md — Create bot/fsm/config.py (StateConfig dataclass, FSM_CONFIG dict for all 18 states)
- [x] 09-02-PLAN.md — Create bot/steps.py (handle_row_input, handle_seat_input, handle_confirmation)

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
**Plans:** 4 plans

Plans:
- [x] 10-01-PLAN.md — Create bot/router.py (Router class, register_all() with enforced ordering)
- [x] 10-02-PLAN.md — Wire router into bot/main.py, replace 7 register_handlers() calls
- [x] 10-03-PLAN.md — Gap closure: Add /exit command handler and register in router
- [x] 10-04-PLAN.md — Gap closure: Integrate FSM_CONFIG into router and add auth guard enforcement

---

### Phase 11: Handler Migration

**Goal:** Удалить мёртвый код (register_handlers, closure-обёртки, ручной command dispatch) из всех 7 файлов хендлеров и подключить shared infrastructure (steps.py, texts.py, constants.py).
**Depends on:** Phase 10
**Requirements:** MIG-01, MIG-02, MIG-03, MIG-04, MIG-05, MIG-06, MIG-07, MIG-08, MIG-09
**Success Criteria** (what must be TRUE):
  1. Все существующие боты-флоу (создание брони, удаление, оплата, резервы, должники) работают идентично — ни один сценарий не сломан
  2. В кодовой базе нет ни одной функции `register_handlers()` и ни одной closure-обёртки для инъекции storage
  3. bot/main.py содержит только импорты модулей хендлеров (для срабатывания декораторов) и один вызов `bot.labeler.load(router.labeler)`
  4. Каждый файл хендлера мигрирован атомарно: в одном коммите новые декораторы + удаление старой регистрации + обновление main.py
**Plans:** 8 plans

**Status:** Complete (2026-02-19)

Plans:
- [x] 11-01-PLAN.md — Migrate reservation.py: remove dead code, wire steps.py/texts.py/Btn
- [x] 11-02-PLAN.md — Migrate deletion.py: remove dead code, wire steps.py/texts.py/Btn
- [x] 11-03-PLAN.md — Migrate reserve.py: remove dead code + command dispatch, wire steps.py/texts.py/Btn
- [x] 11-04-PLAN.md — Migrate commands.py: remove dead code, wire texts.py, add MSG_EXIT_FULL
- [x] 11-05-PLAN.md — Migrate menu.py: remove dead code + command dispatch, wire Btn/texts.py
- [x] 11-06-PLAN.md — Migrate payment.py: remove dead code, wire Btn/texts.py
- [x] 11-07-PLAN.md — Migrate debtors.py: remove dead code, wire texts.py, verify "Обновить"
- [x] 11-08-PLAN.md — Verification pass: confirm zero dead code remains across bot/

---

### Phase 12: Navigation UX

**Goal:** Билетеры получают интуитивную навигацию: /cancel возвращает на предыдущий шаг, /exit сбрасывается в IDLE, ранняя валидация ряда предотвращает бесполезный ввод мест.
**Depends on:** Phase 11
**Requirements:** NAV-01, NAV-02, NAV-03
**Success Criteria** (what must be TRUE):
  1. Билетер в середине операции (например, вводит номера мест) нажимает /cancel — бот возвращает его к предыдущему шагу (ввод ряда), а не в IDLE
  2. Билетер нажимает /exit из любого состояния — FSM сбрасывается в IDLE с подтверждающим сообщением
  3. Билетер вводит ряд без доступных мест для текущей операции — бот сразу сообщает об этом и не запрашивает номера мест
  4. Весь BACK_MAP для всех 16 состояний определён до начала реализации — нет состояний с неопределённым поведением /cancel
**Status:** Complete (2026-02-19)
**Plans:** 2 plans

Plans:
- [x] 12-01-PLAN.md — Rewrite cancel_handler for FSM_CONFIG back-step navigation (NAV-01)
- [x] 12-02-PLAN.md — Add early row validation to 4 row-input handlers (NAV-03)

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
| 7. Bug Fix | v0.2 | 1/1 | Complete | 2026-02-19 |
| 8. Foundation | v0.2 | 3/3 | Complete | 2026-02-19 |
| 9. FSM Config + Steps | v0.2 | 2/2 | Complete | 2026-02-19 |
| 10. Router | v0.2 | 4/4 | Complete | 2026-02-19 |
| 11. Handler Migration | v0.2 | 8/8 | Complete | 2026-02-19 |
| 12. Navigation UX | v0.2 | 2/2 | Complete | 2026-02-19 |

---

*Roadmap updated: 2026-02-19 — Phase 12 complete (2/2 plans, v0.2 milestone complete)*

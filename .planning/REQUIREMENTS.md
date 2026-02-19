# Requirements — v0.2 Рефакторинг архитектуры бота

**Milestone:** v0.2
**Created:** 2026-02-19
**Status:** Defined

---

## v0.2 Requirements

### Bug Fixes

- [ ] **BUG-01**: Fix context switch state restoration — `BotState(original_state)` instead of raw string in `context_switch_handler` (menu.py:325)

### Constants & Texts

- [ ] **CONST-01**: Create `bot/constants.py` with `Btn` StrEnum for all button labels, `Cmd` StrEnum for all commands, and `ALL_COMMANDS` frozenset derived from `Cmd`
- [ ] **CONST-02**: Update `bot/keyboards.py` to use `Btn.*` instead of raw string literals
- [ ] **TEXT-01**: Create `bot/texts.py` consolidating all user-facing prompt and error message strings with `.format()` parameters

### FSM Configuration

- [ ] **FSM-01**: Create declarative state machine config — per-state definition of: handler function, allowed input type, validators/checkers, auth guard (admin/seller/any), forward transition(s), back state. Single source of truth for all bot behavior.

### Shared Steps

- [ ] **STEP-01**: `handle_row_input()` in `bot/steps.py` — validates row number, checks layout, returns typed result (`RowResult`); used by reservation, deletion, reserve flows
- [ ] **STEP-02**: `handle_seat_input()` in `bot/steps.py` — parses seat range string, validates against layout and availability, returns typed result (`SeatResult`); used by reservation, deletion, reserve flows
- [ ] **STEP-03**: `handle_confirmation()` in `bot/steps.py` — handles yes/no confirmation input, returns `Optional[bool]`; used by deletion confirm, reserve remove confirm flows

### Router

- [ ] **RTR-01**: Create `bot/router.py` with `Router` class that reads FSM config to auto-register handlers with automatic storage injection and auth guards
- [ ] **RTR-02**: Universal command interceptor — commands (`/start`, `/help`, `/cancel`, `/exit`) intercepted and handled from any FSM state, not just MAIN_MENU and RESERVE_ACTION
- [ ] **RTR-03**: `register_all()` enforces handler registration order: forwarded-message handler first, then command handlers, then state handlers

### Handler Migration

- [ ] **MIG-01**: Migrate `bot/handlers/reservation.py` to pure handler functions consumed by FSM config + shared steps
- [ ] **MIG-02**: Migrate `bot/handlers/deletion.py` to pure handler functions + shared steps
- [ ] **MIG-03**: Migrate `bot/handlers/reserve.py` to pure handler functions + shared steps
- [ ] **MIG-04**: Migrate `bot/handlers/commands.py` to pure handler functions
- [ ] **MIG-05**: Migrate `bot/handlers/menu.py` to pure handler functions, remove command dispatch elif block
- [ ] **MIG-06**: Migrate `bot/handlers/payment.py` to pure handler functions
- [ ] **MIG-07**: Migrate `bot/handlers/debtors.py` to pure handler functions
- [ ] **MIG-08**: Remove all `register_handlers()` functions and closure wrappers from all handler files
- [ ] **MIG-09**: Update `bot/main.py` to use `bot.labeler.load(router.labeler)` instead of per-file `register_handlers()` calls

### Navigation UX

- [ ] **NAV-01**: `/cancel` command navigates back one state via back-state defined in FSM config (not to IDLE)
- [ ] **NAV-02**: New `/exit` command fully resets FSM state to IDLE (current `/cancel` behavior)
- [ ] **NAV-03**: Early row validation — when user enters a row number, immediately check if that row has relevant seats for the current operation (e.g., no booked seats for deletion, no reserved seats for reserve removal) before prompting for seat numbers

---

## Future Requirements

- [ ] Phase 6 (Статистика и полировка) — deferred from v0.1 to post-refactoring milestone
- [ ] State name or Redis key renames — risky during partial migration; all 16 state names stay identical in v0.2
- [ ] History-stack back navigation — `BACK_MAP` / FSM config back-state is sufficient; no need for runtime history stack

## Out of Scope

- **New business logic or flows** — refactoring only, same DB operations, same audit log entries
- **New features or capabilities** — no new user-facing features beyond navigation UX improvements
- **Web interface changes** — web app is unchanged
- **Database schema changes** — no model or migration changes
- **Redis key format changes** — FSM storage format stays the same

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| BUG-01 | — | Pending |
| CONST-01 | — | Pending |
| CONST-02 | — | Pending |
| TEXT-01 | — | Pending |
| FSM-01 | — | Pending |
| STEP-01 | — | Pending |
| STEP-02 | — | Pending |
| STEP-03 | — | Pending |
| RTR-01 | — | Pending |
| RTR-02 | — | Pending |
| RTR-03 | — | Pending |
| MIG-01 | — | Pending |
| MIG-02 | — | Pending |
| MIG-03 | — | Pending |
| MIG-04 | — | Pending |
| MIG-05 | — | Pending |
| MIG-06 | — | Pending |
| MIG-07 | — | Pending |
| MIG-08 | — | Pending |
| MIG-09 | — | Pending |
| NAV-01 | — | Pending |
| NAV-02 | — | Pending |
| NAV-03 | — | Pending |

---

*19 requirements across 7 categories | 3 future | 5 out of scope*
*Created: 2026-02-19*

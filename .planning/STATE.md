# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-19)

**Core value:** Ни одно место не может быть продано дважды
**Current focus:** v0.2 — Phase 11: Handler Migration (in progress)

## Current Position

Phase: 11 of 12 (Handler Migration) — In progress
Plan: 2 of 8 in current phase
Status: In progress — 11-02 complete (deletion.py migrated)
Last activity: 2026-02-19 — Completed 11-02-PLAN.md (deletion.py migration)

Progress: [███████████████░░░░░] 73% (v0.1 complete, v0.2 phases 7-11 in progress)

## Performance Metrics

**Velocity:**
- Total plans completed: 19 (13 v0.1 + 6 v0.2)
- Average duration: ~5 min
- Total execution time: ~1.3 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 | 1 | ~8 min | 8 min |
| Phase 2 | 4 | ~15 min | ~4 min |
| Phase 3 | 3 | ~7 min | ~2 min |
| Phase 4 | 2 | ~9 min | ~5 min |
| Phase 5 | 2 | ~4 min | ~2 min |
| Phase 8 | 3 | ~7 min | ~2 min |
| Phase 9 | 2 | ~3 min | ~1.5 min |
| Phase 10 plan 01 | 1 | ~2 min | 2 min |
| Phase 10 plan 02 | 1 | ~1 min | 1 min |
| Phase 10 plan 03 | 1 | ~1 min | 1 min |
| Phase 10 plan 04 | 1 | ~2 min | 2 min |

**Recent Trend:**
- Last 5 plans: fast (AI-assisted, minutes each)
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

- [v0.2 scoping] /cancel → назад на шаг, /exit → IDLE — более естественная навигация для билетеров
- [v0.2 scoping] Ранняя валидация ряда: проверять наличие мест до запроса номеров мест
- [v0.2 arch] Router читает FSM config для авто-регистрации хендлеров (FSM-01 is the config, RTR-01 reads it)
- [v0.2 arch] Каждый файл хендлера мигрируется атомарным коммитом (new decorators + remove old + main.py update)
- [07-bug-fix] BotState restoration: BotState(stored_string.split(':')[-1]) handles both "BotState:value" and plain "value" formats
- [07-bug-fix] Idle guard checks raw string against "idle" — modern "BotState:idle" passes guard, but extracted value is still "idle", giving correct BotState.IDLE
- [08-foundation] StrEnum members ARE strings — Btn.ADD == "Добавить" is True, no .value needed
- [08-foundation] PAY_ALL_PREFIX = "Все " (trailing space) — dynamic button uses f"{Btn.PAY_ALL_PREFIX}{count}"
- [08-foundation] ALL_COMMANDS = frozenset(Cmd) — auto-derived, no manual sync needed
- [08-foundation] texts.py: 62 constants, ERR_*/PROMPT_*/MSG_* naming, .format() placeholders, zero imports/callables
- [08-foundation] texts.py not yet wired into handlers — Phase 11 handles import wiring
- [08-foundation] keyboards.py: 19 Btn.* usages, 0 raw strings in Text() calls
- [09-fsm-config] FSM_CONFIG keyed by BotState enum member (not string) — type-safe access
- [09-fsm-config] handler=None in Phase 9; Phase 10 Router wires real handlers to avoid premature coupling
- [09-fsm-config] bot/fsm/config.py NOT exported from __init__.py — imported directly to prevent circular import risk
- [09-fsm-config] auth_guard Literal "any"|"seller"|"admin" — no UserRole import needed in config layer
- [09-steps] Lazy imports in handle_row_input/handle_seat_input/handle_confirmation — avoids circular imports at module level
- [09-steps] availability mode builds dynamic error message inline — occupancy detail is too dynamic for a static texts.py constant
- [09-steps] handle_confirmation is the canonical Btn.CONFIRM/CANCEL comparison location — handlers never compare raw strings directly
- [10-router] Router uses self.labeler (BotLabeler) NOT bot.on — wired to bot in 10-02 via bot.labeler.load(router.labeler)
- [10-router] start_handler/help_handler registered directly (no _wrap) — only take (message,); debtors handlers same
- [10-router] All bot.handlers.* imports lazy (inside _register_* methods) — prevents circular imports
- [10-02] Router(storage=redis_storage) uses local variable directly — more explicit than bot.state_dispenser
- [10-02] BaseStateGroup import removed from main.py — was unused after handler module imports removed
- [10-03] exit_handler message "Сессия завершена" distinct from cancel_handler "Операция отменена" — Phase 12 uses this to differentiate hard reset vs back-navigation
- [10-03] exit_handler NOT added to legacy register_handlers() — it will be removed atomically in Phase 11
- [10-04] get_user_role() returns Optional[UserRole] (not bool) — enables router to distinguish seller vs admin guard levels
- [10-04] _with_auth_guard() imports get_user_role lazily inside the method — consistent with existing lazy import pattern
- [10-04] Auth failure clears FSM state via storage.delete() — prevents user from getting stuck in an unauthorized state
- [10-04] _register_states() iterates FSM_CONFIG (not handler_map) — FSM_CONFIG is the canonical iteration source per RTR-01
- [11-02] handle_seat_input(mode="membership") covers both not-in-reservation and paid-seat checks in deleting_seats_handler
- [11-02] Steps imports in deletion.py kept lazy inside function bodies — consistent with 09-steps circular-import avoidance pattern

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 11] debtors.py не полностью прочитан в ходе research — перед миграцией прочитать и проверить обработку кнопки "Обновить"
- [Phase 12] BACK_MAP для AWAITING_ROW неоднозначен: состояние достигается из разных точек входа. Определить весь BACK_MAP до начала реализации.

## Session Continuity

Last session: 2026-02-19T20:10:50Z
Stopped at: Completed 11-02-PLAN.md. deletion.py migrated — register_handlers() and 4 closures removed, handle_row_input/handle_seat_input(mode="membership")/handle_confirmation wired in, texts.* constants used throughout.
Resume file: None

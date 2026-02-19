# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-19)

**Core value:** Ни одно место не может быть продано дважды
**Current focus:** v0.2 — Phase 9 (next)

## Current Position

Phase: 8 of 12 (Foundation — constants.py, texts.py, keyboards.py) — COMPLETE
Plan: 3 of 3 in phase 8 complete
Status: Phase 8 complete
Last activity: 2026-02-19 — Completed 08-03-PLAN.md (bot/keyboards.py)

Progress: [█████████░░░░░░░░░░░] 47% (v0.1 complete, v0.2 phase 8 all 3 plans done)

## Performance Metrics

**Velocity:**
- Total plans completed: 14 (13 v0.1 + 1 v0.2)
- Average duration: ~5 min
- Total execution time: ~1.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 | 1 | ~8 min | 8 min |
| Phase 2 | 4 | ~15 min | ~4 min |
| Phase 3 | 3 | ~7 min | ~2 min |
| Phase 4 | 2 | ~9 min | ~5 min |
| Phase 5 | 2 | ~4 min | ~2 min |

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
- [08-01] PAY_ALL_PREFIX = "Все " (trailing space) in Btn for startswith(); dynamic button label stays as f-string in keyboards.py
- [08-01] ALL_COMMANDS = frozenset(Cmd) — auto-derived, no manual sync needed
- [08-02] bot/texts.py: 62 constants, ERR_*/PROMPT_*/MSG_* naming, .format() placeholders (not f-strings), zero imports/callables
- [08-02] ERR_DB_CHECK_BOOKING added (not in research baseline) — found in reservation.py context-switch branch
- [08-03] keyboards.py: all Text() calls use Btn.* members; dynamic button is f"{Btn.PAY_ALL_PREFIX}{count}"; 19 Btn.* usages, 0 raw strings

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 11] debtors.py не полностью прочитан в ходе research — перед миграцией прочитать и проверить обработку кнопки "Обновить"
- [Phase 12] BACK_MAP для AWAITING_ROW неоднозначен: состояние достигается из разных точек входа. Определить весь BACK_MAP до начала реализации.

## Session Continuity

Last session: 2026-02-19 17:59 UTC
Stopped at: Completed 08-03-PLAN.md (bot/keyboards.py — Btn.* migration, phase 8 complete)
Resume file: None

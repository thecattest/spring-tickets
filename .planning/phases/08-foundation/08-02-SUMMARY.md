---
phase: 08-foundation
plan: 02
subsystem: ui
tags: [bot, texts, string-constants, i18n, messages]

# Dependency graph
requires:
  - phase: 07-bug-fix
    provides: stable handler codebase to audit for user-facing strings
provides:
  - bot/texts.py with 62 module-level string constants covering all handler-level user-facing messages
affects:
  - phase-11 (handler migration — will import from bot.texts)
  - phase-08-plan-03 (keyboards.py — sibling plan, same phase)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "texts.py as single source of truth: all handler-level user-facing strings are module-level constants in bot/texts.py"
    - "Static strings: plain string assignment (e.g., ERR_CONTEXT_LOST = '...')"
    - "Parameterized strings: named .format() placeholders, NOT f-strings (e.g., MSG_SEATS_ADDED with {count}, {row}, etc.)"
    - "Naming convention: ERR_* for errors, PROMPT_* for user input requests, MSG_* for confirmations/info"

key-files:
  created:
    - bot/texts.py
  modified: []

key-decisions:
  - "62 constants (exceeded 50+ minimum): complete audit of all 7 handler files yielded more strings than RESEARCH.md baseline estimated"
  - "WELCOME and HELP as multi-line string concatenations (no f-strings, explicit newlines) to match handler source"
  - "MSG_CANCEL_FULL and MSG_CANCELLED kept separate (commands.py has two distinct cancel messages)"
  - "ERR_DB_CHECK_BOOKING added (not in RESEARCH.md baseline) — found in reservation.py context-switch path"

patterns-established:
  - "Pattern: bot.texts is import-only (no side effects, no callables) — safe to import anywhere"
  - "Pattern: .format() templates are discoverable by searching for '{' in bot/texts.py"

# Metrics
duration: 2min
completed: 2026-02-19
---

# Phase 8 Plan 02: Bot Texts Module Summary

**62 module-level string constants in bot/texts.py consolidating all user-facing bot prompts, errors, and messages from all 7 handler files, with zero imports and zero callables**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-19T17:54:58Z
- **Completed:** 2026-02-19T17:56:54Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created bot/texts.py as the single source of truth for all handler-level user-facing strings
- 62 constants covering all 7 handler files (commands, menu, deletion, payment, reservation, debtors, reserve)
- All parameterized strings use named .format() placeholders — not f-string syntax
- Zero imports, zero functions — file is purely static string constants

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bot/texts.py with all user-facing string constants** - `de6170b` (feat)

**Plan metadata:** see docs commit below

## Files Created/Modified
- `bot/texts.py` — 62 module-level string constants: ERR_*, PROMPT_*, MSG_*, WELCOME, HELP, and parameterized templates

## Decisions Made
- Added ERR_DB_CHECK_BOOKING (not in RESEARCH.md baseline): found in reservation.py context-switch path — "Ошибка при проверке брони. Попробуйте позже."
- Kept MSG_CANCEL_FULL and MSG_CANCELLED as distinct constants: commands.py uses two different cancel messages (one detailed with instructions, one brief)
- WELCOME and HELP use string concatenation with explicit \n (matches source exactly, no f-strings)
- MSG_CANCELLED_BRIEF added alongside MSG_CANCELLED for "Отменено." (deletion/reserve flows) vs "Операция отменена." (commands.py)

## Deviations from Plan

None - plan executed exactly as written. One additional constant discovered during source audit (ERR_DB_CHECK_BOOKING) added inline.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- bot/texts.py is importable and verified: 62 constants, no functions, no imports
- Ready for Phase 11 handler migration (wiring via `from bot.texts import ...`)
- Phase 08-03 (keyboards.py Btn.* update) can proceed independently — no dependency on texts.py

---
*Phase: 08-foundation*
*Completed: 2026-02-19*

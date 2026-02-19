---
phase: 11
plan: 04
subsystem: bot-handlers
tags: [commands, texts, dead-code-removal, migration]

dependency_graph:
  requires:
    - "10-router: Router owns all handler registrations"
    - "08-foundation: texts.py with 62 constants"
  provides:
    - "commands.py: clean, no dead code, all messages via texts.*"
    - "texts.py: extended with MSG_EXIT_FULL and MSG_EXIT_SHORT"
  affects:
    - "11-05 through 11-08: remaining handler migrations follow same pattern"

tech_stack:
  added: []
  patterns:
    - "texts.* constants replace inline multiline strings in handlers"

key_files:
  created: []
  modified:
    - "bot/handlers/commands.py"
    - "bot/texts.py"

decisions:
  - "MSG_EXIT_FULL added to texts.py (not kept inline) — mirrors MSG_CANCEL_FULL pattern, keeps all strings in one place"

metrics:
  duration: "~1 min"
  completed: "2026-02-19"
---

# Phase 11 Plan 04: Commands Handler Migration Summary

**One-liner:** commands.py dead-code removed; inline strings replaced with texts.WELCOME, texts.HELP, texts.MSG_CANCEL_FULL, texts.MSG_EXIT_FULL; MSG_EXIT_FULL/MSG_EXIT_SHORT added to texts.py.

## What Was Done

Migrated `bot/handlers/commands.py` as part of the Phase 11 handler migration pass.

### Changes to bot/handlers/commands.py

1. Removed `register_handlers(bot: Bot)` function (dead code — Router owns registration since Phase 10)
2. Removed `cancel_with_storage` inner closure (dead code — Router injects storage via `_with_auth_guard`)
3. Changed import from `from vkbottle.bot import Bot, Message` to `from vkbottle.bot import Message` (Bot no longer needed)
4. Added `from bot import texts`
5. `start_handler`: replaced 14-line inline multiline string with `texts.WELCOME`
6. `help_handler`: replaced 33-line inline multiline string with `texts.HELP`
7. `cancel_handler`: replaced inline `"Операция отменена. Состояние сброшено.\n\nЧтобы начать заново, перешлите сообщение клиента."` with `texts.MSG_CANCEL_FULL`; replaced `"Операция отменена."` fallback with `texts.MSG_CANCELLED`
8. `exit_handler`: replaced inline `"Сессия завершена. Состояние сброшено.\n\nЧтобы начать заново, перешлите сообщение клиента."` with `texts.MSG_EXIT_FULL`; replaced `"Сессия завершена."` fallback with `texts.MSG_EXIT_SHORT`

Handler signatures unchanged: `start_handler(message)`, `help_handler(message)`, `cancel_handler(message, storage)`, `exit_handler(message, storage)`.

### Changes to bot/texts.py

Added two new constants in the "Cancel messages" section after `MSG_CANCELLED`:

```python
MSG_EXIT_FULL = (
    "Сессия завершена. Состояние сброшено.\n"
    "\n"
    "Чтобы начать заново, перешлите сообщение клиента."
)

MSG_EXIT_SHORT = "Сессия завершена."
```

These mirror the existing `MSG_CANCEL_FULL` / `MSG_CANCELLED` pair, consistent with the ERR_*/MSG_* naming convention.

## Verification Results

All four checks passed:

- `python3 -c "from bot.handlers.commands import start_handler, help_handler, cancel_handler, exit_handler"` — OK
- `grep -n "register_handlers" bot/handlers/commands.py` — empty (exit code 1)
- `grep -n "from vkbottle.bot import Bot" bot/handlers/commands.py` — empty (exit code 1)
- `python3 -c "from bot.texts import MSG_EXIT_FULL, MSG_EXIT_SHORT; print(MSG_EXIT_FULL[:20])"` — prints "Сессия завершена. Со"

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Add MSG_EXIT_FULL to texts.py (not keep inline) | Mirrors MSG_CANCEL_FULL pattern established in Phase 9. All user-facing strings belong in texts.py per architecture decision [08-foundation]. |

## Commits

| Hash | Message |
|------|---------|
| 4da2aea | feat(11-04): migrate commands.py to texts.py constants |

## Next Phase Readiness

Phase 11 continues with plans 05-08 (menu.py, payment.py, debtors.py, verification pass).

No blockers introduced. The migration pattern established here (remove register_handlers + closures, remove Bot import, add `from bot import texts`, replace inline strings) is identical for all remaining handler files.

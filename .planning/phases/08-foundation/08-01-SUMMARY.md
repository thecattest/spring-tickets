---
phase: 08-foundation
plan: "01"
subsystem: constants
tags: [StrEnum, constants, bot, python-stdlib]

dependency-graph:
  requires: []
  provides:
    - bot/constants.py: "Btn StrEnum (16 members), Cmd StrEnum (9 members), ALL_COMMANDS frozenset"
  affects:
    - phase-08-plan-02: "keyboards.py imports Btn.* from constants"
    - phase-08-plan-03: "texts.py may reference Btn/Cmd names in docstrings"
    - phase-09-onwards: "All handler migration uses Cmd.* for registration and dispatch"

tech-stack:
  added: []
  patterns:
    - "StrEnum for button labels: members compare equal to raw strings (Btn.ADD == 'Добавить')"
    - "frozenset(Cmd) for O(1) command membership check"

key-files:
  created:
    - bot/constants.py
  modified: []

decisions:
  - "PAY_ALL_PREFIX = 'Все ' (trailing space) defined in Btn for startswith() detection; dynamic button label remains f-string in keyboards.py"
  - "ALL_COMMANDS derived from frozenset(Cmd) — auto-complete, no manual maintenance needed"

metrics:
  duration: "~1 min"
  completed: "2026-02-19"
---

# Phase 8 Plan 1: Constants Summary

**One-liner:** Btn/Cmd StrEnum + ALL_COMMANDS frozenset from stdlib enum.StrEnum — single source of truth for all button labels and slash commands.

## What Was Built

`bot/constants.py` — new file providing:

- `Btn(StrEnum)`: 16 members covering all keyboard button labels grouped by keyboard function
- `Cmd(StrEnum)`: 9 members covering all slash commands (Russian and English variants)
- `ALL_COMMANDS: frozenset[str]` — derived from `frozenset(Cmd)` for O(1) membership testing

## Key Implementation Details

All members inherit from `StrEnum` (stdlib since Python 3.11; Python 3.14 is in use). This means:
- `Btn.ADD == "Добавить"` is `True`
- `Cmd.CANCEL == "/Отмена"` is `True`
- No `.value` access needed anywhere in the codebase

The `PAY_ALL_PREFIX = "Все "` member (trailing space) handles the dynamic `"Все {N}"` button pattern: detection uses `text.startswith(Btn.PAY_ALL_PREFIX)`, not equality. The actual button label is still generated as `f"Все {booked_count}"` in keyboards.py.

`ALL_COMMANDS` is a `frozenset[str]` auto-derived from `frozenset(Cmd)` — all 9 command strings included without manual maintenance.

## Decisions Made

1. **PAY_ALL_PREFIX in Btn, not a separate constant:** The `"Все "` prefix logically belongs to the button-label namespace. Placing it in `Btn` groups it with other button strings.
2. **ALL_COMMANDS auto-derived:** Using `frozenset(Cmd)` means adding a new command to `Cmd` automatically includes it in `ALL_COMMANDS` — no dual-maintenance.

## Verification Results

```
Btn members (16): CANCEL_CMD, HELP_CMD, DEBTORS_CMD, RESERVE_CMD, ADD, DELETE, DELETE_ALL,
                  PAYMENT, ADD_MORE, DONE, CONFIRM, CANCEL, YES, NO, REFRESH, PAY_ALL_PREFIX
Cmd members (9): START, HELP, HELP_EN, CANCEL, CANCEL_EN, DEBTORS, DEBTORS_EN, RESERVE, RESERVE_EN
ALL_COMMANDS (9): /cancel, /debtors, /help, /reserve, /start, /Должники, /Отмена, /Резерв, /Справка
All assertions passed.
```

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash    | Type | Description                                        |
|---------|------|----------------------------------------------------|
| 538af31 | feat | add Btn/Cmd StrEnum and ALL_COMMANDS frozenset     |

## Next Phase Readiness

Phase 08 Plan 02 (keyboards.py using Btn.*) can proceed immediately. `bot/constants.py` is importable with no dependencies beyond stdlib.

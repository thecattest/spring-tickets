---
phase: 10-router
verified: 2026-02-19T19:05:41Z
status: gaps_found
score: 2/4 must-haves verified
gaps:
  - truth: "Команды /start, /help, /cancel, /exit работают из любого из 16 FSM-состояний"
    status: failed
    reason: "/exit command is not registered anywhere in the codebase — no handler, no labeler registration"
    artifacts:
      - path: "bot/router.py"
        issue: "_register_commands() registers /start, /help, /cancel, /reserve, /debtors, Обновить — but NOT /exit"
      - path: "bot/handlers/commands.py"
        issue: "No exit_handler function defined — /cancel handler exists but /exit does not"
    missing:
      - "exit_handler function in bot/handlers/commands.py (or equivalent)"
      - "Registration of /exit (and optionally Russian alias) in router._register_commands()"
  - truth: "Router читает FSM config и автоматически регистрирует хендлеры с инъекцией storage и проверкой auth guard"
    status: failed
    reason: "Router does not read FSM_CONFIG at all — state list is hardcoded manually; no auth guard check is applied during or after registration"
    artifacts:
      - path: "bot/router.py"
        issue: "_register_states() contains a manually written list of 17 (BotState, handler) tuples; FSM_CONFIG import is absent; no auth guard enforcement"
      - path: "bot/fsm/config.py"
        issue: "FSM_CONFIG with auth_guard fields exists and is populated for all 18 states, but router.py never imports or reads it"
    missing:
      - "import FSM_CONFIG from bot.fsm.config in router.py"
      - "Iterate FSM_CONFIG instead of hardcoded tuple list (or use FSM_CONFIG to validate the list)"
      - "Auth guard check wired into _wrap() or a separate guard wrapper (reads FSM_CONFIG[state].auth_guard and validates message.from_id role)"
---

# Phase 10: Router Verification Report

**Phase Goal:** Центральный роутер заменяет 7 функций register_handlers() и 14 closure-обёрток; команды перехватываются из любого FSM-состояния.
**Verified:** 2026-02-19T19:05:41Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Команды /start, /help, /cancel, **/exit** работают из любого из 16 FSM-состояний | FAILED | /exit not registered; only /cancel present in router._register_commands() |
| 2 | Router читает FSM config и авторегистрирует хендлеры с инъекцией storage **и проверкой auth guard** | FAILED | Router never imports FSM_CONFIG; state list is hardcoded; no auth guard enforcement exists |
| 3 | register_all() гарантирует порядок: forwarded first, command handlers, state handlers | VERIFIED | Lines 58-60 of router.py call _register_forwarded() → _register_commands() → _register_states() in exact order |
| 4 | bot/main.py использует bot.labeler.load(router.labeler) вместо register_handlers() | VERIFIED | Line 66 of main.py: `bot.labeler.load(router.labeler)`; grep confirms zero register_handlers() calls in main.py |

**Score:** 2/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bot/router.py` | Router class with register_all(), _wrap(), 3 registration groups | VERIFIED | 206 lines, all 5 methods present, no stubs, exported as Router |
| `bot/main.py` | Uses Router(storage=redis_storage).register_all() + bot.labeler.load() | VERIFIED | 103 lines, Router import at line 21, router block at lines 63-66 |
| `bot/handlers/commands.py` | exit_handler function for /exit command | MISSING | File has start_handler, help_handler, cancel_handler — no exit_handler |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| bot/router.py | bot/fsm/states.py | BotState import | WIRED | Line 24: `from bot.fsm.states import BotState` |
| bot/router.py | bot/fsm/storage.py | RedisStorage type hint | WIRED | Line 25: `from bot.fsm.storage import RedisStorage` |
| bot/router.py | bot/handlers/* | lazy imports inside methods | WIRED | All handler imports inside _register_* methods, not at module level |
| bot/router.py | bot/fsm/config.py | FSM_CONFIG for auto-registration | NOT WIRED | bot/router.py never imports FSM_CONFIG; config.py is never referenced |
| bot/main.py | bot/router.py | Router import + instantiation | WIRED | Line 21: `from bot.router import Router`; line 64: `router = Router(storage=redis_storage)` |
| bot/main.py | bot.labeler | labeler.load() transfer | WIRED | Line 66: `bot.labeler.load(router.labeler)` |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| RTR-01: Router reads FSM config, auto-registers with storage injection and auth guards | BLOCKED | Router does not read FSM_CONFIG; auth guard not applied |
| RTR-02: /start, /help, /cancel, /exit intercepted from any FSM state | BLOCKED | /exit not registered in router or handler files |
| RTR-03: register_all() enforces forwarded → commands → states order | SATISFIED | Verified in router.py lines 58-60 |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None | — | — | — |

No stubs, TODO comments, or placeholder patterns found in the two files created by this phase.

### Human Verification Required

None — all gaps are structural and fully verifiable from code.

### Gaps Summary

**Two gaps block full goal achievement:**

**Gap 1: /exit command missing**

The ROADMAP success criterion and RTR-02 requirement explicitly list `/exit` alongside `/start`, `/help`, `/cancel`. No `exit_handler` function exists in `bot/handlers/commands.py` and no registration for `/exit` (or a Russian alias) appears in `bot/router.py._register_commands()`. The remaining commands (/start, /help, /cancel) do work from any FSM state via the text-rule-before-state-rule ordering.

**Gap 2: Router does not read FSM_CONFIG; no auth guard enforcement**

RTR-01 requires the router to "read FSM config to auto-register handlers with automatic storage injection and auth guards." The router delivers storage injection via `_wrap()` correctly, but FSM_CONFIG is never imported or consulted. The 17-state list in `_register_states()` is a manually written tuple list identical in structure to what FSM_CONFIG provides. Auth guard fields (`auth_guard: Literal["any", "seller", "admin"]`) exist on every StateConfig entry in `bot/fsm/config.py` but are never read, so no per-message role check is applied at the router layer.

These two gaps are independent — fixing one does not unblock the other.

**What is working well:**
- Enforced registration order (forwarded → commands → states) is implemented correctly
- `bot.labeler.load(router.labeler)` pattern replaces all 7 `register_handlers()` call sites
- Storage injection via `_wrap()` is clean and reusable
- Lazy handler imports prevent circular import issues
- `bot/main.py` has zero `register_handlers()` calls remaining

---

_Verified: 2026-02-19T19:05:41Z_
_Verifier: Claude (gsd-verifier)_

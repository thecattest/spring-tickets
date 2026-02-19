# Project Research Summary

**Project:** Tickets VK Bot — Architecture Refactoring (Phase 2)
**Domain:** FSM-based VK bot code deduplication and navigation UX
**Researched:** 2026-02-19
**Confidence:** HIGH

## Executive Summary

This project is a focused code-quality refactoring of a production VK bot built on vkbottle 4.x with Redis-backed FSM state. The bot manages multi-step ticket reservation flows and currently suffers from four duplicated validation blocks, 14 manual closure wrappers for storage injection, and command interception logic hand-copied across two handler files. The refactoring goal is to extract shared step primitives, centralize string constants and user-facing text, and replace per-file `register_handlers()` functions with a thin custom Router that injects storage automatically and intercepts commands universally.

The recommended approach follows a strict bottom-up dependency order: `constants.py` (StrEnum for button/command strings) first, then `texts.py` (user-facing strings), then `keyboards.py` update, then `steps.py` (shared row/seat/confirmation primitives), then `router.py` (handler registry with universal command interception), and finally atomic per-file handler migration. This order ensures each new artifact is testable in isolation before anything depends on it, and allows the bot to run in a mixed old/new state during migration without double-firing handlers.

The three critical risks to manage are: (1) `storage.set()` silently drops all payload keys not passed in the call — every step function that writes state must round-trip the full context dict; (2) handler registration order in vkbottle is evaluation order — the forwarded-message handler must be registered before state handlers or it will never fire during active flows; and (3) a pre-existing bug in `context_switch_handler` stores a raw string back into state storage instead of a reconstructed `BotState` member, leaving users stuck after pressing "Нет" — this must be fixed before any other migration begins.

## Key Findings

### Recommended Stack

All stack components are already in place. No new dependencies are needed. The refactoring uses only what is installed: vkbottle 4.x (verified from `.venv` source), Python 3.14's stdlib `StrEnum` (3.11+, no third-party library required), and the existing Redis-backed `RedisStorage`. `BotBlueprint` is explicitly deprecated in the installed vkbottle version (`@deprecated(category=FutureWarning)` in `blueprint.py`) and must not be used for code separation.

**Core technologies:**
- `enum.StrEnum` (stdlib): single-source string constants for button labels and commands — instances pass `isinstance(x, str)` so they work directly in vkbottle `text=` params and keyboard builders with no casting
- Custom `Router` class (new, wraps `bot.on.message()`): replaces 7 `register_handlers()` functions and 14 closure wrappers — holds storage reference, provides `@on_state`/`@on_command` decorators, guarantees command handler registration order
- `steps.py` return-value protocol (not callbacks): step functions return `RowResult`/`SeatResult`/`Optional[bool]`; callers decide state transitions — this keeps steps independently testable and stateless

**Critical version note:** `BotState('awaiting_row')` correctly reconstructs `BotState.AWAITING_ROW` on Python 3.14; back-navigation must store `.value` strings in context payload, never the full `"BotState:awaiting_row"` repr.

### Expected Features

See FEATURES.md for full details and testability criteria.

**Must have (table stakes — refactoring is incomplete without these):**
- `bot/constants.py` with `Btn` and `Cmd` StrEnums — eliminates all raw string literals in keyboard builders and handler if/elif chains
- `bot/steps.py` with `handle_row_input()`, `handle_seat_input()`, `handle_confirmation()` — collapses 4+4+3 duplicated blocks into 3 shared functions
- `bot/router.py` with universal command interceptor — commands currently silently ignored in 14 of 16 FSM states
- All 7 handler files migrated to `@router` decorators — the infra is worthless until handlers use it
- Fix state enum bug in `context_switch_handler` (`BotState(original_state)` not raw string) — latent production bug

**Should have (differentiators, low effort):**
- `bot/texts.py` — centralizes all user-facing strings; without it, string duplication persists even after step extraction
- "Go back" for `/Отмена` command — scoped change from IDLE-reset to parent-state navigation; one `BACK_MAP` dict, not a history stack

**Defer (not this milestone):**
- New flows or feature additions — strict scope: REFACTORING_PLAN phases 2.1-2.7 only
- State name or Redis key renames — dangerous during partial migration; all 16 state names stay identical
- History-stack back navigation — over-engineering; inline `BACK_MAP` is sufficient

### Architecture Approach

The architecture follows a flat component graph with no circular dependencies. vkbottle's handler dispatch is a flat list evaluated in registration order with `blocking=True` stopping at first match — command handlers registered before state handlers win unconditionally. The new `Router` wraps a `BotLabeler` instance and exposes it for `bot.labeler.load(router.labeler)` in `main.py`, which is the official vkbottle composition mechanism. Steps are pure async functions that receive `Message` and return typed result objects; they never call `storage.set()` directly.

**Major components:**
1. `bot/constants.py` — `Btn` and `Cmd` StrEnums, `ALL_COMMANDS` frozenset; no imports from `bot/`
2. `bot/texts.py` — prompt strings and error messages with format parameters; imports `bot.config` and `bot.utils.layout` only
3. `bot/steps.py` — `handle_row_input()`, `handle_seat_input()`, `handle_confirmation()`; returns result objects, never transitions state
4. `bot/router.py` — `Router` class wrapping `BotLabeler`; holds `RedisStorage` reference; `@on_state`, `@on_command`, `@on_message` decorators; `register_all()` enforces forwarded-first ordering
5. `bot/handlers/*.py` (7 files) — consume router decorators and step functions; contain only flow-specific logic (which context key to update, which state to transition to)
6. `bot/main.py` — instantiates `Router(storage)`, imports all handler modules (decorators fire at import time), calls `bot.labeler.load(router.labeler)`

### Critical Pitfalls

See PITFALLS.md for full details including warning signs and prevention strategies.

1. **`storage.set()` silently drops all payload keys not passed** — every context write must read the full context dict first, mutate it, then write `**context`; never pass only the changed key; test with a multi-key context round-trip
2. **Forwarded message handler fires after state handlers if registration order is wrong** — must be registered before state handlers in `register_all()`; verify manually: forward a message while in AWAITING_ROW should get context-switch prompt, not a row-validation error
3. **Context switch "Нет" restores a raw state string, not a `BotState` member** — `storage.set(peer_id, BotState(original_state), ...)` not `storage.set(peer_id, original_state, ...)`; fix before any migration begins
4. **Partial migration leaves duplicate routes active** — both old and new handlers fire for same state; each handler file migration must be atomic: new decorators + remove old `register_handlers()` call + update `main.py` in one commit
5. **"Добавить" string collision between MAIN_MENU and RESERVE_ACTION keyboards** — never use `@router.on_text("Добавить")` stateless; always route via `@router.on_state(BotState.MAIN_MENU)` so state prevents ambiguity

## Implications for Roadmap

Based on research, suggested phase structure (matches REFACTORING_PLAN phases 2.1-2.7):

### Phase 1: Bug Fix — Context Switch State Restoration

**Rationale:** This is a latent production bug that would be invisible during migration testing if context switch is not explicitly tested. Fixing it first establishes a known-good baseline and prevents the bug from being masked by migration noise. It is one line: `BotState(original_state)` instead of `original_state` in `menu.py:325`.
**Delivers:** `context_switch_handler` correctly restores users to their previous state after pressing "Нет"
**Addresses:** FEATURES.md table-stakes item "Fix state enum restoration"; PITFALLS.md Pitfall 4
**Avoids:** Discovering this bug late in migration when multiple changes obscure root cause

### Phase 2: Foundation — Constants, Texts, Keyboards

**Rationale:** `constants.py` has zero dependencies and enables all downstream work. `texts.py` is also leaf-level. Both must exist before `steps.py` can reference them. Keyboard updates are zero-behavior-change and can be verified immediately.
**Delivers:** `Btn`/`Cmd` StrEnums with `ALL_COMMANDS` frozenset; `texts.py` with all prompt/error strings; `keyboards.py` updated to use `Btn.*`
**Uses:** stdlib `StrEnum` (Python 3.11+, no new deps); existing `bot.utils.layout` for row range
**Implements:** constants and texts components from architecture dependency graph
**Avoids:** Pitfall 11 ("Добавить" collision) — document in `constants.py` that `Btn.ADD` must only be used inside state-guarded handlers, not stateless text routing

### Phase 3: Shared Step Primitives

**Rationale:** `steps.py` depends on constants and texts but nothing in handlers. Building it before the router means it can be unit-tested in isolation. The 4+4+3 duplicated blocks (row input, seat input, confirmation) are the highest-leverage deduplication target.
**Delivers:** `handle_row_input()`, `handle_seat_input()`, `handle_confirmation()` with unit tests verifying multi-key context round-trips
**Implements:** steps component; establishes return-value protocol
**Avoids:** Pitfall 1 (context round-trip) — write the explicit round-trip test here; Pitfall 6 (callback complexity) — use return-value protocol not callbacks

### Phase 4: Router with Universal Command Interception

**Rationale:** `router.py` depends only on vkbottle internals and `fsm/*` — it does not depend on handler files. Must be built before any handler migration begins. Registration order invariant (forwarded-first, then commands, then states) must be documented and enforced here.
**Delivers:** `Router` class with `@on_state`, `@on_command`, `@on_message` decorators; `register_all()` with explicit ordering; `bot.labeler.load(router.labeler)` wired in `main.py`
**Implements:** router component; replaces 7 `register_handlers()` call sites
**Avoids:** Pitfall 2 (forwarded handler order) — register forwarded handler first in `register_all()`; Pitfall 3 (command interceptor completeness) — derive `ALL_COMMANDS` from `Cmd` enum, never a separate list; Pitfall 9 (CONTEXT_SWITCH_CONFIRM special case) — document and handle in interceptor

### Phase 5: Handler Migration (Atomic Per-File)

**Rationale:** Each file migration is independent and delivers immediate value once the router and steps exist. Migration order: `reservation.py` (simplest, most duplication), `deletion.py` (high duplication), `reserve.py` (high duplication), `commands.py`, `menu.py` (remove elif re-dispatch), `payment.py`, `debtors.py`.
**Delivers:** All 7 handler files using `@router.on_state`/`@router.on_command`; all `register_handlers()` functions deleted; `main.py` import list updated
**Implements:** complete migration of handlers component
**Avoids:** Pitfall 5 (dual registration) — each file migration commit is atomic: new decorators + remove old registration + `main.py` update in one commit; Pitfall 10 (ID confusion) — always use keyword args when calling `show_main_menu()`

### Phase 6: Back-Navigation for `/Отмена`

**Rationale:** Deferred to its own phase because it is a UX change, not a code deduplication task. Must define `BACK_MAP` upfront covering all 16 states before implementing any back-nav behavior, or ambiguous states will silently do the wrong thing.
**Delivers:** `BACK_MAP` dict in `bot/fsm/states.py`; `/Отмена` command navigates to parent state instead of always resetting to IDLE; special handling for `AWAITING_ROW` (context-dependent) and `CONTEXT_SWITCH_CONFIRM` (use existing "Нет" logic)
**Avoids:** Pitfall 8 (ambiguous back semantics) — define entire map upfront, never incrementally

### Phase Ordering Rationale

- Phase 1 before everything: the context switch bug is a production issue that migration testing will not catch reliably; fixing it first isolates it
- Phases 2 and 3 before Phase 4: `constants.py` and `texts.py` are prerequisites for `steps.py`; `steps.py` is a prerequisite for meaningful handler migration
- Phase 4 before Phase 5: no handler migration should begin without the router existing to receive it; dual registration (Pitfall 5) is impossible if the router does not yet exist
- Phase 6 last: it is a behavior change, not a refactoring; keeping it separate makes the refactoring scope clear and auditable

### Research Flags

Phases with standard patterns (no additional research needed):
- **Phase 1:** Single line fix, verified against vkbottle dispenser source; pattern fully documented in STACK.md
- **Phase 2:** StrEnum is stdlib; keyboard update is mechanical; both are zero-risk
- **Phase 3:** Return-value protocol is standard Python; step function signatures are fully specified in ARCHITECTURE.md
- **Phase 4:** `BotLabeler.load()` and handler ordering verified from vkbottle source; no unknowns

Phases that may benefit from a focused research pass:
- **Phase 5 (debtors.py):** `debtors.py` was not fully read during research. The "Обновить" button handling (Pitfall 12) needs verification of how the debtors state machine works before migrating. Read the file before writing migration code.
- **Phase 6 (back-navigation):** The `AWAITING_ROW` ambiguity (Pitfall 8: user arrived from IDLE vs MAIN_MENU vs SEAT_ADDITION_MENU) requires tracing all entry points to that state before finalizing `BACK_MAP`. One research pass over the forwarded message handler scenarios in `reservation.py` is recommended.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All findings sourced from installed vkbottle 4.x source code and live Python 3.14 runtime tests; no external docs needed |
| Features | HIGH | Direct codebase inspection with exact line counts; duplication is verified and quantified (4+4+3 blocks) |
| Architecture | HIGH | vkbottle dispatch chain, handler list ordering, `BotLabeler.load()` all verified from installed source |
| Pitfalls | HIGH | All pitfalls derived from reading actual codebase files with exact line references; no speculative pitfalls |

**Overall confidence:** HIGH

### Gaps to Address

- **`debtors.py` not fully read:** Pitfall 12 notes the "Обновить" handler risk but the full debtors handler was not inspected. Read `bot/handlers/debtors.py` before the Phase 5 debtors migration commit.
- **`show_main_menu()` cross-handler import:** ARCHITECTURE.md recommends keeping it in `menu.py` (Option C) as a one-directional import. This is acceptable for now but creates a dependency from `reservation.py`, `deletion.py`, and `payment.py` on `menu.py`. If `menu.py` ever imports from those files, a circular import will occur. Flag this for review if new features cause bidirectional dependencies.
- **`/Отмена` back-navigation scope:** FEATURES.md calls this a "nice-to-have, very low effort, but is a UX change not a refactoring." The roadmap includes it as Phase 6, but the product owner should confirm whether it belongs in the same milestone or a separate one before Phase 6 planning begins.

## Sources

### Primary (HIGH confidence)

- `/Users/thecattest/things/projects/Tickets/.venv/lib/python3.14/site-packages/vkbottle/` — installed package source: dispatch chain, handler ordering, BotLabeler.load(), StateRule, BotBlueprint deprecation
- Python 3.14.0 runtime: live tests for StrEnum behavior and `BotState('value')` reconstruction
- `/Users/thecattest/things/projects/Tickets/bot/handlers/*.py` — all 7 handler files; duplication counts and line references verified
- `/Users/thecattest/things/projects/Tickets/bot/fsm/storage.py` — `set()` payload replacement behavior (Pitfall 1 root cause)
- `/Users/thecattest/things/projects/Tickets/REFACTORING_PLAN.md` — project intent and planned patterns
- `/Users/thecattest/things/projects/Tickets/bot/fsm/states.py` — all 16 `BotState` values for PARENT_STATE map

### Secondary (MEDIUM confidence)

- python-telegram-bot enum refactoring PRs (#2708, #3351) — confirmed StrEnum pattern for bot button labels in analogous framework
- WebSearch on FSM back-navigation patterns — confirmed `previous_state` inline storage is correct approach; no vkbottle-native "go back" API exists

### Tertiary (LOW confidence)

- Chatbot cancel UX best practices (WebSearch) — "inline cancel" scoped to step vs "cancel everything" aborting session; informs BACK_MAP design but not authoritative for this specific bot's UX

---
*Research completed: 2026-02-19*
*Ready for roadmap: yes*

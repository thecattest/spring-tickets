# Feature Landscape: VK Bot Architecture Refactoring

**Domain:** FSM-based multi-step VK bot — code deduplication and navigation UX milestone
**Researched:** 2026-02-19
**Confidence:** HIGH (all findings grounded in direct codebase inspection + verified patterns)

---

## Context: What Exists Today

Before categorizing features, the current state sets the baseline:

- 7 handler files, 16 FSM states, 4 distinct multi-step flows
- Row input validation duplicated 4 times (reservation.py, deletion.py, reserve.py x2)
- Seat input validation duplicated 4 times (same files)
- Confirmation handler (Подтвердить/Отмена) duplicated 3 times (deletion.py x2, reserve.py)
- Command dispatch block (`elif text.startswith("/"):`) duplicated in menu.py:177 and reserve.py:83
- All `register_handlers()` functions produce manual closure wrappers (`async def x_with_storage`)
- Button labels are raw strings in both keyboards.py and every handler's if/elif chains
- `/Отмена` resets to IDLE from any state — no "go back one step"
- Commands only intercepted in MAIN_MENU and RESERVE_ACTION states; all other states eat commands silently
- No early validation of row input before forwarded message creates a reservation

Concrete duplication count from inspection:
- `awaiting_row_handler` logic appears verbatim as: `awaiting_row_handler`, `deleting_row_handler`,
  `reserve_adding_row_handler`, `reserve_removing_row_handler` — ~30 lines each
- `parse_seats` + range validation appears verbatim in: `awaiting_seats_handler`,
  `deleting_seats_handler`, `reserve_adding_seats_handler`, `reserve_removing_seats_handler` — ~20 lines each
- Confirmation dispatch (Подтвердить/Отмена/else) appears verbatim in: `deletion_confirm_handler`,
  `cancel_confirm_handler`, `reserve_remove_confirm_handler`

---

## Table Stakes

Features that must be delivered for the refactoring to meet its stated goal. Missing any of these
means the refactoring is incomplete as a code quality exercise.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `bot/constants.py` with `Btn` and `Cmd` StrEnums | Eliminating raw string literals is prerequisite for everything else — keyboards, handlers, tests all reference same source | Low | Python `StrEnum` (3.11+) or `str, Enum` mixin; python-telegram-bot did exactly this refactor (PR #2708, PR #3351) |
| `bot/steps.py` — `handle_row_input()` shared primitive | 4 identical 30-line blocks become 1. Without this, deduplication goal is not achieved | Medium | Must handle: parse int, is_valid_row(), error messages, context update, state transition, prompt |
| `bot/steps.py` — `handle_seat_input()` shared primitive | 4 identical 20-line blocks become 1. Returns `(row, seats)` or `None`; caller handles flow-specific logic | Medium | Does NOT decide what to do with valid seats — that stays in the caller |
| `bot/steps.py` — `handle_confirmation()` shared primitive | 3 identical dispatch blocks become 1. Takes `on_confirm`, `on_cancel` callbacks | Medium | Must reshow keyboard on unknown input |
| `bot/router.py` — central registry replacing 7 `register_handlers()` | Removes 7×5-line closure wrappers; injects storage automatically | Medium | Auto-injection requires Router to hold storage reference |
| Universal command interceptor in Router | Commands currently silently ignored in 14 of 16 states. Interceptor in `_wrap()` fires before every state handler | Medium | Clears state, then dispatches to command handler. Must NOT fire for IDLE state (infinite loop risk) |
| `bot/texts.py` — all user-facing strings | Without centralizing text, a copy-paste of strings persists even after steps.py extraction; messages.py already handles script generation | Low | Separate from messages.py which is generation logic; texts.py is raw UI copy |
| All 7 handler files migrated to `@router` decorators | Without migration, the Router and steps.py exist but aren't used — no deduplication actually achieved | High (cumulative) | Each handler file is independently migratable; one file = one commit |
| Fix state enum restoration in context_switch_handler | `await storage.set(message.from_id, original_state, ...)` passes raw string; must be `BotState(original_state)` | Low | Currently: line 325 in menu.py passes `original_state` (string) directly |

---

## Differentiators

Features that improve UX or developer experience beyond the minimum deduplication goal. Not
required to call the refactoring "done" but add meaningful value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Go back" in inline Отмена buttons | Currently "Отмена" in deletion_confirm and reserve_remove_confirm returns to MAIN_MENU/RESERVE_ACTION (already correct). The UX gap is `/Отмена` command resetting to IDLE when user is in a sub-step of a flow | Low | Scoped: only change `/Отмена` behavior when in mid-flow states to return to parent menu instead of IDLE. IDLE command still clears fully |
| Early row validation in `handle_row_input` — show seat count eagerly | Currently the row prompt ("Введите номер ряда:") gives no context. After successful row input, seat_count is included in the transition prompt. This is already done — the improvement is to include it in the initial prompt if we can validate row before commit | Low | The REFACTORING_PLAN already plans `handle_row_input` to format seat count in transition prompt; this is the implemented behavior |
| Early validation at forwarded-message stage — check if row number is known | Not currently a feature: reservation is created immediately on forward, regardless of whether the buyer exists or what state things are in. The "early validation" mentioned in the project context refers to validating row input, not pre-reservation checks | Low | The row input validation in `handle_row_input()` is the early validation: it validates before storing context and transitioning, re-prompting on error |
| Flow map documentation in `bot/flows.py` or as module docstring | Machine-readable or at least human-readable state transition map exists in REFACTORING_PLAN.md section 2.7. Moving it into code makes it searchable and helps future devs | Very Low | Optional; has no runtime effect |
| `bot/texts.py` error messages include contextual seat range info | Currently error messages like "Неверный ряд" include the range, but it's computed inline. Centralizing with format params means one place to adjust copy | Low | Already in REFACTORING_PLAN texts.py spec |
| Test coverage for shared step primitives | Once `steps.py` exists as pure functions taking `message` and `storage`, they're independently testable. The bot already has a `bot/tests/` directory | Medium | Valuable because shared steps are high-leverage: a bug there affects all 4 flows |

---

## Anti-Features

Things to explicitly NOT do during this refactoring. These are failure modes confirmed by
inspecting the codebase and by FSM bot refactoring anti-patterns.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| State history stack / "back" button navigation via stored history array | Adds complexity that the flows don't need. The bot's inline "Отмена" buttons already return to the correct parent state (deletion_confirm → MAIN_MENU, reserve_remove_confirm → RESERVE_ACTION). Only `/Отмена` command is the outlier. Don't build a general history stack | Adjust `/Отмена` command behavior specifically: detect if user is in a mid-flow state and return to parent menu. That's one if-block, not a history stack |
| Moving flow-specific validation logic into shared steps | `handle_seat_input()` should validate only format and range — it should NOT check availability (reservation flow), reservation membership (deletion flow), or reserve conflicts (reserve flow). Those are caller concerns | Keep shared steps thin: they handle the parts that are literally identical across flows. Flow-specific checks stay in the handler |
| Merging `confirmation_keyboard` and `context_switch_keyboard` | They serve different intents. Confirmation is "do the thing?", context switch is "switch clients?". Sharing them couples UX decisions | Keep them separate keyboard functions. Both are already one-liners |
| Single mega-handler file | Putting all handlers in one file to "reduce files" would make navigation and per-flow testing harder | Keep handler files per domain (reservation, deletion, reserve, payment, commands). Router handles registration; files handle logic |
| Adding new flows or features during refactoring | Classic scope creep. The /Должники handler, payment flow, and context switch are not being refactored in this milestone | Implement REFACTORING_PLAN phases 2.1-2.7 only. New features get a separate milestone |
| Changing FSM state names or storage key names mid-migration | State names are stored in Redis. Renaming states while handlers are partially migrated leaves users in states that no longer have handlers | Complete migration of a state's handler before renaming anything. All 16 states stay named identically |
| Using a third-party `state_manager` library for back-navigation | The `state_manager` PyPI package supports vkbottle and offers `back_to_pre_state()`. It adds a dependency for a problem that can be solved with 5 lines of inline logic | Store `previous_state` in context for flows that need it; don't introduce a new library |
| Re-prompting with the full message after unknown input in every state | Currently every state has an `else` branch that re-shows the keyboard. This is correct. Do NOT silently ignore unknown input — users who type random text while in a state need feedback | Keep the `else: re-show keyboard` pattern; `handle_confirmation()` already implements this |
| Splitting `handle_row_input` by flow (reservation_row_input, deletion_row_input, etc.) | Defeats the purpose. The entire point is that row validation is identical across flows | One `handle_row_input(message, storage, next_state, prompt=None)` with `next_state` parameterized |

---

## Feature Dependencies

The order in which deliverables must be built:

```
constants.py (Btn, Cmd enums)
    │
    ├─→ keyboards.py updated (references Btn.ADD instead of "Добавить")
    │
    └─→ texts.py (references same Btn/Cmd for consistency in error messages)
         │
         └─→ steps.py (handle_row_input, handle_seat_input, handle_confirmation)
              │      uses: texts.py, layout utils, storage
              │
              └─→ router.py (Router class with command interceptor)
                   │
                   └─→ handler file migration (one file at a time)
                        │
                        └─→ main.py wired up (router.register_all())
```

`constants.py` has no dependencies and can be created first with no risk. Everything else
depends on it. `steps.py` depends on `texts.py` for error messages. Handler migration depends
on both `steps.py` and `router.py` existing.

---

## MVP Recommendation

For the refactoring milestone, the full scope is:

1. `constants.py` — Btn and Cmd StrEnums, update keyboards.py
2. `texts.py` — extract all user-facing strings
3. `steps.py` — three shared primitives (row_input, seat_input, confirmation)
4. `router.py` — Router with storage injection and universal command interceptor
5. Handler migration — all 7 files migrated to @router decorators, using step primitives
6. Fix state enum bug in context_switch_handler

This is the REFACTORING_PLAN Phase 2 scope, which is correct and self-contained.

**Defer to a future milestone:**
- History-stack back navigation: Not needed; inline Отмена buttons already return correctly
- New keyboard layouts or button redesigns: Out of scope
- `/Отмена` returning to parent menu (instead of IDLE): Nice-to-have, very low effort, but is a UX
  change not a refactoring — should be called out explicitly in the milestone spec

---

## Testability Criteria

Each refactoring deliverable has a concrete, testable completion signal:

| Deliverable | Done When |
|-------------|-----------|
| `constants.py` | `grep -r '"Добавить"' bot/` returns 0 results outside constants.py and comments |
| `texts.py` | No inline user-facing strings in handler files (format strings use `texts.X.format(...)`) |
| `steps.py` | `handle_row_input`, `handle_seat_input`, `handle_confirmation` each have unit tests passing |
| `router.py` | `register_handlers()` function deleted from all 7 handler files; manual closures gone |
| Command interceptor | Sending `/Отмена` while in AWAITING_ROW, DELETING_SEATS, RESERVE_COMMENT (etc.) clears state and responds correctly |
| Handler migration | `grep -r 'storage = bot.state_dispenser' bot/handlers/` returns 0 results |
| State enum fix | Context switch "Нет" response correctly restores user to previous state (not to raw string state) |
| Line count | reservation.py < 200 lines, deletion.py < 100 lines, reserve.py < 150 lines |

---

## Sources

- Direct codebase inspection: `/Users/thecattest/things/projects/Tickets/bot/handlers/*.py`,
  `/Users/thecattest/things/projects/Tickets/bot/fsm/states.py`,
  `/Users/thecattest/things/projects/Tickets/bot/keyboards.py`
- Project refactoring plan: `/Users/thecattest/things/projects/Tickets/REFACTORING_PLAN.md`
- python-telegram-bot enum refactoring PRs (confirmed StrEnum pattern for bot button labels):
  https://github.com/python-telegram-bot/python-telegram-bot/pull/2708
  https://github.com/python-telegram-bot/python-telegram-bot/pull/3351
- FSM back-navigation patterns: WebSearch — history stack and `previous_state` storage patterns;
  no vkbottle-native "go back" API found (LOW confidence that any library-native solution exists;
  inline logic is correct approach)
- Chatbot cancel UX: WebSearch — "inline cancel" scoped to step vs "cancel everything" aborting
  session; confirmed best practice is two distinct affordances with clear scope signals
- Python StrEnum: https://docs.python.org/3/library/enum.html (HIGH confidence)

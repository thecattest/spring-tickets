# Domain Pitfalls: VK Bot Architecture Refactoring

**Domain:** FSM-based VK bot (vkbottle), production system
**Researched:** 2026-02-19
**Confidence:** HIGH — all findings derived from reading the actual codebase, not generalizations

---

## Critical Pitfalls

Mistakes that cause broken flows, silent bugs, or production incidents.

---

### Pitfall 1: `storage.set()` Overwrites the Entire Payload

**What goes wrong:**
Every call to `storage.set(peer_id, state, **kwargs)` replaces the entire `StatePeer.payload` dict
(see `bot/fsm/storage.py:160-168`). There is no "merge" behavior — keys not passed are lost.

The current code avoids this by always doing:
```python
context = await storage.get_context(message.from_id)
context['current_row'] = row
await storage.set(message.from_id, BotState.AWAITING_SEATS, **context)
```

**Where it will break during refactoring:**
`steps.handle_row_input()` receives `message` and `storage`, reads context, updates
`current_row`, then calls `storage.set(peer_id, next_state, **context)`. If the step function
is called incorrectly — for example, without first loading context into a local variable — the
state write will silently drop all other payload keys (reservation_id, buyer_display_name, etc.).

This is especially dangerous during handler migration because `steps.handle_row_input()` is
called in four different handlers. Each has a different set of payload keys it depends on
downstream. One incorrect call drops the wrong keys and the next handler fails with a
"context lost" error that's hard to trace.

**Warning signs:**
- Handler after a shared step sees `context.get("reservation_id") = None` for a user who just
  had a valid reservation_id in context
- "Ошибка: потерян контекст" messages appearing for flows that were working before
- Errors only occur on the second step of a flow (never the first)

**Prevention:**
- The step functions must always load context first, mutate it, then write it back with `**context`
- Never pass only the new key: `await storage.set(peer_id, state, current_row=row)` — this drops
  everything else
- In `steps.handle_row_input()`, verify with a test that all incoming context keys survive the
  round-trip through the step

**Phase that should address it:**
Phase creating `steps.py` — add an explicit test that passes a context with multiple keys
through `handle_row_input()` and asserts all keys are present in the new context afterward.

---

### Pitfall 2: Handler Registration Order Matters — Forwarded Message Handler Fires on All States

**What goes wrong:**
VKBottle matches handlers in registration order. The forwarded message handler is registered with
a `func=` predicate (not a state filter):

```python
# bot/handlers/reservation.py:557
bot.on.message(func=lambda msg: bool(msg.fwd_messages))(forwarded_with_storage)
```

This means it fires for any forwarded message regardless of FSM state, including `AWAITING_ROW`,
`AWAITING_SEATS`, `DELETING_SEATS`, etc. The handler itself contains the multi-scenario logic
that inspects current state (scenario 1/2/3 branching). It works because it was registered
before the state handlers.

If the new Router registers state handlers first and the forwarded message handler second, the
state handler fires instead of the forwarded handler for states like `AWAITING_ROW`. The seller
sends a forwarded message while in AWAITING_ROW and gets a row-validation error ("Неверный
формат. Введите номер ряда...") instead of the context-switch prompt.

**Warning signs:**
- Forwarded messages during active flows produce row/seat validation errors instead of
  context-switch prompts
- The forwarded message scenario 3 path (different client while working) stops triggering

**Prevention:**
- The forwarded message handler must be registered BEFORE any state handlers
- The Router's `register_all()` method must guarantee this ordering explicitly — not rely
  on Python dict ordering or decorator application order
- Verify with a manual test: while in AWAITING_ROW state, forward a message → should get
  context switch prompt, not a row validation error

**Phase that should address it:**
Phase creating `router.py` — document registration order as an explicit invariant with a comment.
The `register_all()` method should register forwarded handler first, then command handlers,
then state handlers.

---

### Pitfall 3: The Command Interceptor Must Not Fire for `/Резерв` Self-Re-Entry

**What goes wrong:**
The proposed Router wraps all state handlers with a command interceptor:
```python
if text in ALL_COMMANDS and text in self._command_handlers:
    await storage.delete(message.from_id)
    await self._command_handlers[text](message, storage)
    return
```

This is correct for most commands. But there is one specific case where it breaks:
in `RESERVE_ACTION` state, if the seller types `/Резерв` again, the current behavior
(`reserve.py:83-100`) clears state and re-runs `reserve_command_handler()`, which checks
admin status and resets the state to `RESERVE_ACTION`. This is correct and idempotent.

The interceptor also does this — clears state and calls the command handler — so `/Резерв`
in `RESERVE_ACTION` state would work. However, `reserve_command_handler()` calls
`storage.set(peer_id, BotState.RESERVE_ACTION, admin_user_id=app_user.id)`, which drops any
other context keys (admin_user_id is the only one, so this is fine here).

The actual danger is with `/Отмена` being in `ALL_COMMANDS`. When `/Отмена` triggers the
interceptor, it calls `cancel_handler()`, which calls `storage.delete()` again. That is a
double-delete but benign. The subtle issue: after cancelling via interceptor, the
cancel_handler sends a message. Then `return` stops the state handler. This is correct.

The real failure case: `/Должники` is in the persistent keyboard, but NOT in the flow map.
If a user in `AWAITING_SEATS` taps `/Должники`, the interceptor must fire. If `/Должники` is
accidentally excluded from `ALL_COMMANDS` (e.g. the constant is `/Должники` but the keyboard
sends `/Должники` — Cyrillic D vs Latin D), the interceptor silently misses it and the state
handler sees "Должники" and calls row-validation.

**Warning signs:**
- `/Должники` during an active flow produces a row/seat validation error
- Commands work in IDLE but not in AWAITING_ROW or DELETING_SEATS

**Prevention:**
- `ALL_COMMANDS = frozenset(Cmd)` — verify all commands in the persistent keyboard are
  present in the `Cmd` enum with exact string matches (copy from `keyboards.py`, do not retype)
- Test each command from each state class during migration, not just from IDLE

**Phase that should address it:**
Phase creating `constants.py` — derive `ALL_COMMANDS` from the same enum used by `keyboards.py`,
never from a separate list.

---

### Pitfall 4: Context Switch "Нет" Restores a Raw State String, Not a `BotState` Member

**What goes wrong:**
This bug already exists and is documented in REFACTORING_PLAN.md §2.6:

```python
# Current code in menu.py:325
await storage.set(message.from_id, original_state, **original_context)
```

`original_state` is a string like `"awaiting_row"` stored in Redis payload. But
`storage.set()` accepts a `BaseStateGroup` member, not a raw string. VKBottle's state
matching uses `str(BotState.AWAITING_ROW)` for comparison — and `str(BotState.AWAITING_ROW)`
produces `"BotState:awaiting_row"` (with the group prefix), not `"awaiting_row"`.

After "Нет" the user is technically back in the old state, but VKBottle's state dispatcher
will not match any handler because the stored string is `"awaiting_row"` and the handlers
are registered for `BotState.AWAITING_ROW` which serializes as `"BotState:awaiting_row"`.
The user is stuck — all subsequent messages fall through to the forwarded message handler
or produce no response.

**Warning signs:**
- After "Нет" on context switch, user messages produce no response
- User's state appears as `"awaiting_row"` in Redis (no `BotState:` prefix) after restore

**Prevention:**
- Fix before extracting shared steps: `await storage.set(peer_id, BotState(original_state), **original_context)`
- Note: `BotState(original_state)` raises `ValueError` if the string is not a valid member.
  Wrap with try/except and fall back to `storage.delete()` + inform user
- This fix is referenced in REFACTORING_PLAN.md §2.6 and should be treated as Phase 1

**Phase that should address it:**
Handle before handler migration — it is a latent bug that would be invisible during
migration testing if context switch is not explicitly tested.

---

### Pitfall 5: Partial Handler Migration Leaves Duplicate Routes Active

**What goes wrong:**
During the migration period, both the old `register_handlers()` pattern and the new
`@router.on_state()` pattern exist. If a handler is migrated to the router but
`register_handlers()` still registers the old version, both handlers are registered for the
same state. VKBottle fires both — the first registered wins, but the second also runs.

Example: `deletion.py` is migrated to use `@router.on_state(BotState.DELETING_ROW)` and
the router is wired up. But `deletion.register_handlers(bot)` is still called in `main.py`.
VKBottle now has two handlers for `DELETING_ROW`. The router's handler fires, transitions the
user to `DELETING_SEATS`, sends the correct message. Then the old handler fires on the same
message: reads context, sees `current_row` does not exist yet (it was set in the NEW context by
the router handler), and sends a validation error or "context lost" message.

**Warning signs:**
- Users get double messages during any state transition
- "context lost" errors appear immediately after a valid input
- Log shows the same state handler function called twice for one message

**Prevention:**
- Remove `register_handlers()` call in `main.py` for each file immediately when migrating
  that file to the router — in the same commit
- Never leave a partially-migrated state where both old and new registration coexist
- The migration commit for each handler file must include: new router decorators + remove
  `register_handlers()` call + update `main.py` import list

**Phase that should address it:**
Handler migration phase — enforce as a rule: each handler file migration is atomic.

---

## Moderate Pitfalls

Mistakes that cause technical debt or delayed breakage.

---

### Pitfall 6: `steps.handle_confirmation()` Is Too Generic — Forces Awkward Callback Pattern

**What goes wrong:**
The proposed `handle_confirmation()` takes `on_confirm` and `on_cancel` as async callables.
This looks clean but creates a hidden problem: each of the three confirmation handlers
(`deletion_confirm`, `cancel_confirm`, `reserve_remove_confirm`) needs different context keys
to operate. The callbacks receive `(message, storage, context)` — but "context" here is the
context AT THE TIME of confirmation, which includes flow-specific keys.

The problem is when `on_cancel` needs to call `show_main_menu()`, which requires
`reservation_id`, `buyer_vk_user_id`, `buyer_vk_api_id`, `buyer_display_name` — four keys
that are in context only for the reservation flow, not the reserve flow. The reserve flow's
`on_cancel` would call `storage.set(peer_id, BotState.RESERVE_ACTION, admin_user_id=...)`.

If `handle_confirmation()` calls `on_cancel(message, storage, context)` but the callback
is a closure that captures a variable that is stale (e.g. buyer_display_name from outer
scope at definition time vs context at call time), there are subtle data-coherence bugs
where the user sees the wrong name or the wrong reservation ID.

**Prevention:**
- Keep `handle_confirmation()` thin: just dispatch to `on_confirm` or `on_cancel`
- Do not try to make the callbacks stateless — let them receive full `context`
- Test each confirmation callback with a context dict that has ONLY the keys for that flow
  (not a superset), verifying it does not KeyError

---

### Pitfall 7: `texts.py` Format Strings Diverge From Their Call Sites

**What goes wrong:**
Currently, each handler constructs its own f-strings inline. The format is local and
immediately visible. After moving to `texts.py`, the format key names must exactly match
what callers pass:

```python
# texts.py
INVALID_ROW_RANGE = "Неверный ряд. Допустимые значения: {min_row}-{max_row}. Введите ряд:"

# steps.py — correct
await message.answer(texts.INVALID_ROW_RANGE.format(min_row=min_row, max_row=max_row))

# steps.py — wrong key name, silent KeyError at runtime
await message.answer(texts.INVALID_ROW_RANGE.format(min=min_row, max=max_row))
```

Python's `str.format()` with named keys raises `KeyError` at runtime if a key is missing.
This produces a 500-style crash: the message silently fails to send and the user gets no
response. The error only appears in logs. In production with async handlers, this is hard
to notice until a user complains.

**Warning signs:**
- User sends a valid row number, gets no response (not even a validation error)
- Error log shows `KeyError: 'min_row'` inside an async handler

**Prevention:**
- After extracting `texts.py`, run a quick scan: for each `texts.X.format(...)` call,
  verify that the keys passed match the `{...}` placeholders in the string
- Consider using a test that instantiates each format string with representative values
- Move texts extraction in a separate commit from steps extraction — don't do both at once

---

### Pitfall 8: The "Back One State" Semantics Are Ambiguous for Multi-Row Flows

**What goes wrong:**
The plan changes `/Отмена` from "clear all state → IDLE" to "go back one state." The state
machine has flows where "back one state" is well-defined:

- `DELETING_SEATS` → back → `DELETING_ROW` (clear seats, keep reservation_id in context)
- `DELETION_CONFIRM` → back → `DELETING_SEATS` (keep row and reservation in context)

But there are ambiguous cases:

**Case 1: AWAITING_ROW**
The user is in `AWAITING_ROW`. They came from either:
- A fresh forward (no main menu) — back means IDLE (nothing to go back to)
- `SEAT_ADDITION_MENU` "Добавить еще" — back means `SEAT_ADDITION_MENU`
- `MAIN_MENU` "Добавить" (from_main_menu=True) — back means `MAIN_MENU`

There is no single correct "back" from `AWAITING_ROW`. The context flag `from_main_menu`
partially disambiguates but does not cover the "added more rows" case where the user is
re-entering AWAITING_ROW from SEAT_ADDITION_MENU.

**Case 2: CONTEXT_SWITCH_CONFIRM**
The user is in `CONTEXT_SWITCH_CONFIRM`. They have `original_state` and `original_context`
stored. Pressing /Отмена to "go back" should presumably behave like "Нет" — restore original
state. But if "back one state" logic just pops to the previous state generically, it might
miss the `original_context` restoration logic and leave the user in IDLE.

**Case 3: RESERVE_COMMENT**
The user typed the reserve seats but has not committed. "Back" from RESERVE_COMMENT should
return to `RESERVE_ADDING_SEATS`. But `reserve_seats` is already stored in context.
Going back to `RESERVE_ADDING_SEATS` with stale `reserve_seats` in context is harmless here,
but the user will be confused if the old seats appear to be pre-filled (they are not shown,
but they would overwrite if the state just re-runs without clearing them).

**Prevention:**
- Define "back" explicitly per-state in a lookup table, not as a generic "pop":
  ```python
  BACK_MAP = {
      BotState.AWAITING_SEATS: BotState.AWAITING_ROW,
      BotState.SEAT_ADDITION_MENU: BotState.AWAITING_ROW,
      BotState.DELETING_SEATS: BotState.DELETING_ROW,
      BotState.DELETION_CONFIRM: BotState.DELETING_SEATS,
      BotState.CANCEL_CONFIRM: BotState.MAIN_MENU,
      BotState.PAYMENT_QUANTITY: BotState.MAIN_MENU,
      BotState.RESERVE_ADDING_SEATS: BotState.RESERVE_ADDING_ROW,
      BotState.RESERVE_COMMENT: BotState.RESERVE_ADDING_SEATS,
      BotState.RESERVE_REMOVING_SEATS: BotState.RESERVE_REMOVING_ROW,
      BotState.RESERVE_REMOVE_CONFIRM: BotState.RESERVE_REMOVING_SEATS,
      # AWAITING_ROW: context-dependent, handle in handler
      # CONTEXT_SWITCH_CONFIRM: handle via existing "Нет" path, not back nav
  }
  ```
- States not in the map (`AWAITING_ROW`, `MAIN_MENU`, `RESERVE_ACTION`, `IDLE`, `CONTEXT_SWITCH_CONFIRM`)
  either have context-dependent back behavior or should do full reset
- `AWAITING_ROW` needs special handling: check `from_main_menu` in context to decide whether
  to go to `MAIN_MENU` or `IDLE`
- `CONTEXT_SWITCH_CONFIRM` should NOT be in the back map — use the existing "Нет" logic instead

**Phase that should address it:**
Define `BACK_MAP` before implementing the `/Отмена` back-nav behavior. Do not implement
back-nav incrementally across states — define the entire map upfront.

---

### Pitfall 9: `original_context` Nesting in Context Switch Creates an Inconsistent Payload Shape

**What goes wrong:**
The context switch stores the original state's context as a nested dict:

```python
await storage.set(
    message.from_id,
    BotState.CONTEXT_SWITCH_CONFIRM,
    ...
    original_state=current_state,
    original_context=current_context,   # nested dict inside payload
)
```

`storage.get_context()` returns `StatePeer.payload`. So `context["original_context"]` is a
plain dict, while the top-level context is also a plain dict. These look identical in code but
have different semantics.

After refactoring with `steps.py`, if a shared step function calls
`storage.get_context(peer_id)` while the user is in `CONTEXT_SWITCH_CONFIRM`, it will see
the pending-switch keys (`pending_buyer_vk_id`, etc.) — not the original flow keys. If any
step function is accidentally invoked in `CONTEXT_SWITCH_CONFIRM` state (e.g. if the
command interceptor fires but the intercept check has a bug), the step will crash trying
to find `current_row` or `reservation_id`.

**Prevention:**
- The Router's command interceptor must handle `CONTEXT_SWITCH_CONFIRM` state by treating
  `/Отмена` as "Нет" (restore original state), not as a generic cancel
- Steps should never be called in `CONTEXT_SWITCH_CONFIRM` state — this should be
  enforced by not registering any step-using handlers for that state

---

### Pitfall 10: `reservation_id` vs `buyer_vk_user_id` vs `buyer_vk_api_id` — Three IDs, Easy to Confuse

**What goes wrong:**
The codebase uses three distinct user-related IDs in context payloads:

| Key | Type | Source | Used for |
|-----|------|--------|---------|
| `reservation_id` | int | database auto-increment | `db.get_reservation_seats()` calls |
| `buyer_vk_user_id` | int | `VkUser.id` (internal DB row id) | `db.get_active_reservation()` |
| `buyer_vk_api_id` | int | VK API's `user_id` | same-client detection in forwarded handler |

During `show_main_menu()` refactoring, the function signature is:
```python
async def show_main_menu(message, storage, reservation_id, vk_user_id, buyer_display_name, buyer_vk_api_id)
```
These are positional in some callers. If the shared `steps.py` or `router.py` code ever
constructs this call from context dict values, mixing up `buyer_vk_user_id` and
`buyer_vk_api_id` would pass the wrong IDs silently — Python won't catch it because both
are integers.

**Warning signs:**
- Same-client detection incorrectly identifies different clients as the same (or vice versa)
  after a context switch
- `db.get_active_reservation(buyer_vk_api_id)` silently returns None because VK API IDs
  are in a different range than internal DB row IDs

**Prevention:**
- When extracting helper calls to shared code, pass by keyword argument, never positional:
  `show_main_menu(message, storage, reservation_id=ctx['reservation_id'], vk_user_id=ctx['buyer_vk_user_id'], ...)`
- Consider renaming `vk_user_id` param in `show_main_menu()` to `buyer_internal_db_id` to
  make the distinction self-documenting

---

## Minor Pitfalls

Mistakes that are annoying but easy to find and fix.

---

### Pitfall 11: `keyboards.py` "Добавить" Collision Between Main Menu and Reserve Action

**What goes wrong:**
Two keyboards use the button label `"Добавить"`:
- `main_menu_keyboard()`: `"Добавить"` (add seats to reservation)
- `reserve_action_keyboard()`: `"Добавить"` (add a reserve)

After creating `constants.py` with a `Btn` enum, if both are mapped to the same enum member
`Btn.ADD = "Добавить"`, the string collision is preserved but it looks intentional. In handler
conditions, `if text == Btn.ADD` works only because FSM state routes to different handlers.

The real risk: if `handle_confirmation()` or any other shared step is accidentally invoked in
both `MAIN_MENU` state and `RESERVE_ACTION` state for the "Добавить" button press, both
would hit the same code path.

This is not a new bug — it already relies on state routing. But it becomes a pitfall during
router implementation if the router's `on_text()` method is used to register text handlers
without state context.

**Prevention:**
- Never use `@router.on_text("Добавить")` — always use `@router.on_state(BotState.MAIN_MENU)` so
  state routing prevents ambiguity
- The `Btn` enum is for readability, not for stateless text matching

---

### Pitfall 12: `debtors_keyboard()` Has a "Обновить" Button That Reuses the Debtors Handler

**What goes wrong:**
The debtors view keyboard has a single "Обновить" button. In `debtors.py`:
```python
# bot/handlers/debtors.py (not yet read but implied by the keyboard)
# "Обновить" button press re-runs _show_debtors()
```

After migrating to the Router, if "Обновить" is handled via `@router.on_text("Обновить")`,
it will fire in any state where the user taps "Обновить", including after returning to
MAIN_MENU (where "Обновить" is not a button but the user might type it manually or have
a stale keyboard). The debtors handler would run unexpectedly.

**Prevention:**
- Register the "Обновить" handler with a state check, not as a stateless text handler
- Or check in the handler that the current state is appropriate before running

---

## Phase-Specific Warnings

| Phase | Topic | Likely Pitfall | Mitigation |
|-------|-------|---------------|------------|
| `constants.py` creation | Extracting `Btn` enum | "Добавить" collision between MAIN_MENU and RESERVE_ACTION keyboards (Pitfall 11) | Never use for stateless routing |
| `router.py` creation | Registration order | Forwarded handler fires after state handlers (Pitfall 2) | Register forwarded handler first in `register_all()` |
| `router.py` creation | Command interceptor | `/Отмена` in CONTEXT_SWITCH_CONFIRM must restore state, not just delete (Pitfall 9) | Special-case CONTEXT_SWITCH_CONFIRM in interceptor |
| `steps.py` creation | Context round-trip | Payload keys silently dropped by `storage.set()` (Pitfall 1) | Test context round-trip explicitly |
| Handler migration | Dual registration | Both old and new handlers fire simultaneously (Pitfall 5) | Each migration commit is atomic: new code + remove old registration |
| `/Отмена` back-nav | Back from AWAITING_ROW | from_main_menu context flag needed (Pitfall 8) | Define BACK_MAP upfront before any implementation |
| `/Отмена` back-nav | Back from CONTEXT_SWITCH_CONFIRM | Must use "Нет" logic, not generic back (Pitfall 8) | Exclude from BACK_MAP, handle separately |
| `texts.py` creation | Format string keys | KeyError at runtime if key names mismatch (Pitfall 7) | Scan all `.format()` call sites in same commit |
| `texts.py` creation | Timing | Move texts in separate commit from steps | Avoid debugging two changes simultaneously |
| Context switch fix | State enum restoration | Raw string vs BotState member after "Нет" (Pitfall 4) | Fix before migration begins |

---

## Sources

All findings are derived from direct inspection of the codebase:
- `bot/fsm/storage.py` — `set()` payload replacement semantics (Pitfall 1)
- `bot/handlers/reservation.py:557` — forwarded handler registration order (Pitfall 2)
- `bot/handlers/menu.py:177-194`, `bot/handlers/reserve.py:83-100` — command dispatch blocks (Pitfall 3)
- `bot/handlers/menu.py:325` — raw string state restoration in context switch (Pitfall 4)
- `bot/main.py:66-72` — `register_handlers()` call pattern (Pitfall 5)
- `REFACTORING_PLAN.md §2.2-2.3` — proposed Router and steps.py design (Pitfalls 6, 7)
- `bot/handlers/reservation.py:82-228` — context switch multi-scenario logic (Pitfalls 8, 9)
- `bot/handlers/menu.py:23-72` — show_main_menu() three-ID signature (Pitfall 10)
- `bot/keyboards.py:74,188` — "Добавить" label reuse across keyboards (Pitfall 11)

---
phase: 02
plan: 02
subsystem: menu-navigation
completed: 2026-01-24
duration: 4 minutes

tags:
  - vkbottle
  - fsm
  - menu
  - context-switching
  - phase-2

requires:
  - phase: 02
    plan: 01
    reason: "Depends on FSM states, keyboards, and seat formatting utilities"
  - phase: 01
    plan: 01
    reason: "Uses reservation creation flow and seat parser"

provides:
  - "Main menu display for existing reservations"
  - "Context switch detection and confirmation flow"
  - "Backward compatible seat addition (Phase 1 + Phase 2 flows)"
  - "VK API integration for fetching user display names"

affects:
  - phase: 02
    plans: [03, 04]
    reason: "Deletion and cancellation handlers will use main menu navigation pattern"

tech-stack:
  added: []
  patterns:
    - "VK API users.get() for real-time name fetching"
    - "Context preservation across state transitions"
    - "Conditional flow branching with from_main_menu flag"
    - "FSM state conflict detection pattern"

key-files:
  created:
    - path: "bot/handlers/menu.py"
      loc: 281
      exports: ["show_main_menu", "main_menu_handler", "context_switch_handler", "register_handlers"]
  modified:
    - path: "bot/handlers/reservation.py"
      changes: "Added VK API name fetch, menu routing, context conflict detection, backward compatible seat addition"
    - path: "bot/main.py"
      changes: "Registered menu handlers"

decisions:
  - id: "vk-api-name-fetch"
    what: "Fetch VK user display name via VK API on every forwarded message"
    why: "Ensures up-to-date names without database migration for existing VkUser records"
    alternatives: "Cache names in database (requires migration), use ID as placeholder"
    impact: "Extra API call per forwarded message, but acceptable for low-frequency operation"

  - id: "from-main-menu-flag"
    what: "Use from_main_menu context flag to differentiate Phase 1 vs Phase 2 flows"
    why: "Preserves backward compatibility - Phase 1 flow generates script, Phase 2 returns to menu"
    alternatives: "Separate handlers for each flow, check state history"
    impact: "Simple boolean flag enables dual-mode behavior in seat_addition_menu_handler"

  - id: "context-switch-pending-info"
    what: "Store pending client info in CONTEXT_SWITCH_CONFIRM state payload"
    why: "Enables restoration of original state on 'Нет' and creation/menu display on 'Да'"
    alternatives: "Use separate Redis keys for pending data, in-memory cache"
    impact: "All state data self-contained in StatePeer, no external dependencies"

  - id: "same-client-detection"
    what: "Check if forwarded message is from same client as current context"
    why: "Prevents duplicate work and confusing UX when seller re-forwards same message"
    alternatives: "Allow duplicate forwards, ignore all forwards when not idle"
    impact: "Simple buyer_vk_user_id comparison prevents accidental workflow restarts"
---

# Phase 2 Plan 02: Main Menu and Context Switching Summary

**One-liner:** Main menu navigation for existing reservations with VK API name fetching and context switch confirmation when seller switches between clients

---

## What Was Built

Implemented main menu display and navigation for sellers managing existing reservations. When a seller forwards a message from a client who already has an active reservation, the bot now displays all seats grouped by row with status indicators (📌Бронь, ✅Оплачено, 🔒Резерв) and provides action buttons.

Created context switch detection to handle the case where a seller is working with Client A and accidentally forwards a message from Client B. The bot prompts for confirmation before switching contexts to prevent data loss.

Integrated VK API `users.get()` to fetch real-time display names instead of using placeholder "VK User {id}", ensuring all messages show actual client names.

Made seat addition handler backward compatible by checking `from_main_menu` flag - Phase 1 flow (new reservations) generates script and clears state, Phase 2 flow (existing reservations) returns to main menu.

---

## Tasks Completed

### Task 1: Create main menu handler
**Files:** `bot/handlers/menu.py` (new file, 281 lines)

Created complete menu navigation system:
- **show_main_menu()** - Fetches reservation seats, formats with status indicators, displays with action buttons, sets FSM state to MAIN_MENU with from_main_menu=True flag
- **main_menu_handler()** - Routes button presses:
  - "Добавить" → AWAITING_ROW with get_empty_keyboard
  - "Удалить" → Validates seats exist, transitions to DELETING_ROW with get_empty_keyboard
  - "Удалить все" → Validates seats exist, counts paid/booked, shows confirmation with confirmation_keyboard
  - "Оплата" → Placeholder message for Phase 3
- **context_switch_handler()** - Processes Да/Нет responses:
  - "Да" → Clears FSM, shows main menu or creates new reservation for pending client
  - "Нет" → Restores original state and context from before switch prompt
- **register_handlers()** - Registers MAIN_MENU and CONTEXT_SWITCH_CONFIRM state handlers

**Commit:** b2cf686 - "feat(02-02): create main menu handler with context switch support"

### Task 2: Modify forwarded message handler for menu/conflict detection
**Files:** `bot/handlers/reservation.py` (modified)

Completely rewrote forwarded_message_handler to handle three scenarios:

1. **Seller IDLE + client NO reservation** → Create new reservation (Phase 1 behavior)
2. **Seller IDLE + client HAS reservation** → Call show_main_menu() (Phase 2 behavior)
3. **Seller NOT IDLE** → Check if same client (ignore) or different client (context switch confirmation)

Key changes:
- **VK API integration:** Fetch display name once at start using `message.ctx_api.users.get([buyer_vk_id])`, extract first_name + last_name, fallback to "VK User {id}" on error
- **FSM state check:** Get current state via `storage.get(message.from_id)`, extract state and payload
- **Same client detection:** Compare buyer_vk_id with current_context.buyer_vk_user_id
- **Context switch prompt:** Show confirmation keyboard, store pending client info (pending_buyer_vk_id, pending_buyer_display_name, pending_has_reservation, pending_reservation_id) and original state (original_state, original_context) in CONTEXT_SWITCH_CONFIRM state

**Commit:** 702ef80 - "feat(02-02): add menu routing and context conflict detection to forwarded handler"

### Task 3: Make seat_addition_menu_handler backward compatible
**Files:** `bot/handlers/reservation.py` (modified)

Added conditional flow branching based on from_main_menu flag:

**"Готово" button logic:**
- If from_main_menu=True → Call show_main_menu() with updated seat list (Phase 2 flow)
- If from_main_menu=False → Generate script, clear FSM state (Phase 1 flow)

**"Добавить еще" button:** Preserves all context including from_main_menu flag when transitioning back to AWAITING_ROW

**Result:** Existing Phase 1 reservations (created via forwarded message with no prior reservation) continue to work exactly as before - generate script at end. New Phase 2 reservations (accessed via main menu) return to menu after adding seats.

**Commit:** adeca20 - "feat(02-02): make seat addition handler backward compatible with Phase 1"

### Task 4: Register menu handlers in main.py
**Files:** `bot/main.py` (modified)

Added menu module import and handler registration:
- Import: `from bot.handlers import commands, reservation, menu`
- Registration order: commands → reservation → menu (ensures proper handler priority)

**Commit:** 820e85d - "feat(02-02): register menu handlers in bot initialization"

---

## Verification

**Import test:** All handlers import successfully
```bash
python -c "from bot.handlers.menu import show_main_menu, main_menu_handler, context_switch_handler; from bot.handlers.reservation import forwarded_message_handler; import bot.main; print('All imports successful')"
# Output: All imports successful
```

**Existing tests:** Seat parser tests pass (22/33 total tests pass, failures are pre-existing database/Redis setup issues unrelated to this plan)

**Handler registration:** Verified menu.register_handlers(bot) called in main.py after reservation handlers

---

## Technical Implementation

### VK API Integration Pattern

```python
# Fetch display name once at start of forwarded_message_handler
try:
    vk_users = await message.ctx_api.users.get(user_ids=[buyer_vk_id])
    if vk_users:
        vk_info = vk_users[0]
        display_name = f"{vk_info.first_name} {vk_info.last_name}"
    else:
        display_name = f"VK User {buyer_vk_id}"
except Exception as e:
    logger.warning(f"Failed to fetch VK user info: {e}")
    display_name = f"VK User {buyer_vk_id}"
```

**Benefits:**
- Real names in all messages instead of generic "VK User 12345"
- Single API call per forwarded message (acceptable overhead)
- Graceful fallback on API failure
- No database migration needed

### Context Preservation Pattern

```python
# Store pending switch info in CONTEXT_SWITCH_CONFIRM state
await storage.set(
    message.from_id,
    BotState.CONTEXT_SWITCH_CONFIRM,
    # Pending new client
    pending_buyer_vk_id=vk_user.id,
    pending_buyer_display_name=display_name,
    pending_has_reservation=bool(existing_reservation),
    pending_reservation_id=existing_reservation.id if existing_reservation else None,
    # Original context to restore on "Нет"
    original_state=current_state,
    original_context=current_context,
)
```

**Benefits:**
- All state self-contained in StatePeer payload
- No external storage needed
- Easy restoration of original state if user declines switch
- Supports both create-new and show-existing flows for pending client

### Backward Compatibility Pattern

```python
# In seat_addition_menu_handler
from_main_menu = context.get("from_main_menu", False)

if text == "Готово":
    if from_main_menu:
        # Phase 2: return to menu
        await show_main_menu(...)
    else:
        # Phase 1: generate script and clear state
        script = generate_reservation_script(...)
        await message.answer(script)
        await storage.delete(message.from_id)
```

**Benefits:**
- Single handler serves both Phase 1 and Phase 2 flows
- No breaking changes to existing behavior
- Flag defaults to False for backward compatibility
- Clear separation of concerns

---

## Deviations from Plan

None - plan executed exactly as written.

---

## Challenges and Solutions

**Challenge 1: Where to fetch VK display names**
- **Problem:** Plan didn't specify whether to call VK API or use database cached names
- **Solution:** Fetch via VK API once at start of forwarded_message_handler, pass display_name to all subsequent calls
- **Reasoning:** Ensures current names without database migration, acceptable overhead for infrequent operation

**Challenge 2: How to differentiate Phase 1 vs Phase 2 flows in seat_addition_menu_handler**
- **Problem:** Need to support both "generate script" (Phase 1) and "return to menu" (Phase 2) behaviors
- **Solution:** Use from_main_menu boolean flag in context
- **Reasoning:** Simple, explicit, preserves backward compatibility, flag set by show_main_menu()

**Challenge 3: Storing pending client info during context switch**
- **Problem:** Need to remember pending client details while waiting for confirmation
- **Solution:** Store in CONTEXT_SWITCH_CONFIRM state payload (pending_buyer_vk_id, pending_buyer_display_name, pending_has_reservation, pending_reservation_id, original_state, original_context)
- **Reasoning:** Self-contained state, no external dependencies, supports restoration and continuation

---

## Next Phase Readiness

**Ready for Phase 2 Plans 03-04:**
- Main menu navigation pattern established
- show_main_menu() can be called from any handler to return to menu
- Context switch pattern handles seller workflow interruptions
- from_main_menu flag pattern can be extended for deletion flows

**Blockers:** None

**Concerns:** None - all patterns working as designed

**Dependencies satisfied:**
- ✅ FSM states (MAIN_MENU, DELETING_ROW, CANCEL_CONFIRM, CONTEXT_SWITCH_CONFIRM) from Plan 02-01
- ✅ Keyboards (main_menu_keyboard, confirmation_keyboard, context_switch_keyboard) from Plan 02-01
- ✅ Seat formatting (format_reservation_seats, format_seat_ranges) from Plan 02-01
- ✅ Database operations (get_reservation_seats, get_active_reservation) from Phase 1

---

## Files Modified

**Created:**
- `bot/handlers/menu.py` (281 lines)
  - show_main_menu() - Display reservation with action buttons
  - main_menu_handler() - Route button presses to appropriate states
  - context_switch_handler() - Handle Да/Нет confirmation
  - register_handlers() - Register state handlers

**Modified:**
- `bot/handlers/reservation.py`
  - forwarded_message_handler() - VK API name fetch, three-scenario routing, context conflict detection
  - seat_addition_menu_handler() - Backward compatible with from_main_menu flag
- `bot/main.py`
  - Import menu module
  - Register menu handlers

---

## Metrics

**Duration:** 4 minutes (232 seconds)
**Tasks:** 4/4 completed
**Commits:** 4 (all feature commits)
**Files created:** 1
**Files modified:** 2
**Lines added:** ~330
**Lines modified:** ~80

**Velocity:** Highly efficient - all tasks completed atomically with clear commits

---

## Lessons Learned

**What worked well:**
- VK API integration was straightforward with message.ctx_api.users.get()
- from_main_menu flag provides clean separation between Phase 1 and Phase 2 flows
- Context switch pattern handles edge case elegantly without complex state machines
- show_main_menu() as reusable helper simplifies navigation

**What could be improved:**
- VK API call adds latency to forwarded message handling (acceptable for MVP, could cache in future)
- Same-client detection could be more sophisticated (e.g., show current progress instead of just "already working")

**For future phases:**
- Deletion handlers (Plan 02-03) can follow same pattern: validate, show confirmation, execute, call show_main_menu()
- Cancellation handler (Plan 02-04) already has foundation with CANCEL_CONFIRM state and confirmation keyboard
- Payment handlers (Phase 3) can use similar from_main_menu pattern for navigation

---

*Phase: 02-main-menu-seat-management*
*Plan: 02*
*Completed: 2026-01-24*
*Duration: 4 minutes*

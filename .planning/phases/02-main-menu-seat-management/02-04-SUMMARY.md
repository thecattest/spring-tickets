---
phase: 02-main-menu-seat-management
plan: 04
subsystem: bot-handlers
tags: [vkbottle, fsm, context-switching, bug-fix]

# Dependency graph
requires:
  - phase: 02-main-menu-seat-management
    provides: Main menu navigation and context switching infrastructure
provides:
  - Same-client detection using VK API ID comparison
  - Consistent buyer_vk_api_id flow through all FSM states
  - Fixed forwarded message handler to recognize repeat messages from same client
affects: [phase-3-payment-recording]

# Tech tracking
tech-stack:
  added: []
  patterns: [VK API ID as primary client identity for same-client detection]

key-files:
  created: []
  modified:
    - bot/handlers/menu.py
    - bot/handlers/reservation.py
    - bot/handlers/deletion.py

key-decisions:
  - "Use buyer_vk_api_id (VK API user ID) for same-client detection instead of buyer_vk_user_id (database primary key)"
  - "Store both buyer_vk_user_id (database ID) and buyer_vk_api_id (VK API ID) in FSM context for dual purposes"

patterns-established:
  - "Pattern: Store buyer_vk_api_id in all FSM states for same-client detection across state transitions"
  - "Pattern: Pass buyer_vk_api_id to show_main_menu for context persistence"

# Metrics
duration: 3min
completed: 2026-01-24
---

# Phase 2 Plan 4: Fix Same-Client Detection Bug Summary

**Fixed same-client detection bug by comparing VK API IDs instead of VK API ID against database primary key, enabling graceful handling of multiple forwards from the same client**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-24T06:25:05Z
- **Completed:** 2026-01-24T06:28:14Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Fixed same-client detection to compare VK API IDs (both from VK API) instead of VK API ID against database primary key
- Updated show_main_menu signature and all 8 external callers to pass buyer_vk_api_id parameter
- Stored buyer_vk_api_id in FSM context at all reservation entry points
- Ensured buyer_vk_api_id flows through all state transitions (main menu, deletion, cancellation, context switching)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add VK API ID parameter to show_main_menu and update ALL callers** - `d0d1bb9` (feat)
2. **Task 2: Store VK API ID in FSM context at reservation entry points** - `b08c5a1` (feat)
3. **Task 3: Fix same-client comparison and update context switch handler** - `093ffb7` (fix)

## Files Created/Modified
- `bot/handlers/menu.py` - Added buyer_vk_api_id parameter to show_main_menu, updated context_switch_handler to extract and pass pending_buyer_vk_api_id
- `bot/handlers/reservation.py` - Fixed same-client comparison (line ~69-71), stored buyer_vk_api_id in FSM context at entry points, updated show_main_menu calls
- `bot/handlers/deletion.py` - Updated all 6 show_main_menu calls to pass buyer_vk_api_id, extracted buyer_vk_api_id in deletion_confirm_handler and cancel_confirm_handler

## Decisions Made

**1. Dual ID storage in FSM context**
- Rationale: buyer_vk_user_id (database primary key) needed for database operations, buyer_vk_api_id (VK API user ID) needed for same-client detection
- Impact: Both IDs stored and passed through all state transitions without replacing existing functionality

**2. Update all show_main_menu callers systematically**
- Rationale: Adding required parameter means all 8 callers must be updated atomically to prevent breakage
- Impact: Comprehensive update across 3 files (menu.py, reservation.py, deletion.py) ensures consistent buyer_vk_api_id flow

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for Phase 3: Payment Recording**
- Same-client detection working correctly - seller can forward multiple messages from same client without interruption
- buyer_vk_api_id stored in all FSM states and available for future payment flows
- Main menu navigation and context switching fully functional with fixed same-client handling

**No blockers or concerns**

---
*Phase: 02-main-menu-seat-management*
*Completed: 2026-01-24*

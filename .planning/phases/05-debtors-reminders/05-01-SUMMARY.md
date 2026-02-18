---
phase: 05-debtors-reminders
plan: "01"
name: debtors-command
subsystem: bot-commands
tags: [debtors, reminders, sqlalchemy, vkbottle, admin, seller]

dependency-graph:
  requires:
    - "04-02"  # reserve handler established bot handler pattern and get_app_user_by_vk_id
    - "03-01"  # db.py patterns, SessionLocal usage, SEAT_PRICE config
    - "02-01"  # UserRole.ADMIN enum used for role check
  provides:
    - "get_debtors(seller_id) DB function"
    - "get_all_active_sellers() DB function"
    - "debtors_keyboard() with Обновить button"
    - "format_debtors_list() and format_reminder() message formatters"
    - "/debtors command handler with admin/seller filtering"
    - "Обновить button refresh handler"
  affects:
    - "05-02"  # cron script imports get_debtors, get_all_active_sellers, format_reminder

tech-stack:
  added: []
  patterns:
    - "correlated subquery for BOOKED seat count per reservation (SQLAlchemy)"
    - "timedelta-based threshold (NOT SQL INTERVAL — SQLite incompatible)"
    - "stateless command handler without FSM (same as /start and /help)"
    - "shared _show_debtors() helper to avoid duplication between command and button handlers"

key-files:
  created:
    - "bot/handlers/debtors.py"
  modified:
    - "bot/utils/db.py"
    - "bot/keyboards.py"
    - "bot/messages.py"
    - "bot/main.py"
    - "bot/handlers/commands.py"

decisions:
  - id: "D1"
    summary: "get_debtors uses Python timedelta, not SQL INTERVAL"
    rationale: "SQLite does not support SQL INTERVAL syntax; Python-side timedelta is consistent with how all other datetime operations work in the codebase"
  - id: "D2"
    summary: "Correlated subquery for BOOKED seat count"
    rationale: "Avoids GROUP BY complexity; cleanly filters reservations with zero BOOKED seats using WHERE booked_count > 0"
  - id: "D3"
    summary: "/debtors and Обновить are stateless handlers (no FSM)"
    rationale: "Debtor view is read-only; no multi-step flow needed; follows commands.py pattern (same as /start and /help)"
  - id: "D4"
    summary: "Shared _show_debtors() private helper"
    rationale: "Both debtors_command_handler and refresh_debtors_handler execute identical logic; extracted to avoid code duplication"
  - id: "D5"
    summary: "Admin (role=ADMIN) passes seller_id=None to see all debtors; seller passes seller_id=app_user.id"
    rationale: "Matches CONTEXT.md spec: 'seller sees only their own, admin sees all'"
  - id: "D6"
    summary: "format_reminder() takes list of dicts (same as format_debtors_list)"
    rationale: "Cron script (Plan 02) calls get_debtors(seller_id=seller.id) and passes result directly to format_reminder(); no additional transformation needed"

metrics:
  tasks-completed: 2
  tasks-total: 2
  commits: 2
  duration: "~2 minutes"
  completed: "2026-02-18"
---

# Phase 5 Plan 01: Debtors Command Summary

**One-liner:** Stateless /debtors command with admin/seller filtering using correlated BOOKED-seat subquery and timedelta threshold.

## What Was Built

Implemented the `/debtors` command for viewing unpaid reservations, including all DB query logic, message formatters, and handler registration.

### DB functions (bot/utils/db.py)

**`get_debtors(seller_id=None)`**
- Computes threshold as `datetime.utcnow() - timedelta(days=7)` (not SQL INTERVAL)
- Uses a correlated subquery to count unreleased BOOKED seats per reservation
- Filters: ACTIVE state, last_activity_at <= threshold, booked_count > 0
- JOINs VkUser for buyer display name
- Optional seller_id filter for seller-scoped view
- Sorted by last_activity_at ASC (oldest first)
- Returns list of dicts with reservation_id, buyer_display_name, booked_seat_count, debt_amount, days_since_activity, last_activity_at

**`get_all_active_sellers()`**
- Returns active AppUsers with vk_user_id IS NOT NULL
- Used by cron script (Plan 02) to enumerate message recipients

### Keyboard (bot/keyboards.py)

**`debtors_keyboard()`**
- Single "Обновить" button with PRIMARY color
- Follows Keyboard(one_time=False, inline=True) pattern

### Message formatters (bot/messages.py)

**`format_debtors_list(debtors)`**
- Header: "Должники ({count}):"
- Per debtor: name line + indented "Мест: N | Долг: N руб. | Дней: N"

**`format_reminder(debtors)`**
- Header: "Напоминание о должниках ({count}):"
- Per debtor: compact one-line "{name} -- N мест, N руб., N дн. без активности"
- Used by cron script for VK messages to sellers

### Handler (bot/handlers/debtors.py)

- `_show_debtors(message)`: shared helper resolving user, filtering by role, querying and formatting
- `debtors_command_handler(message)`: handles `/debtors` text command
- `refresh_debtors_handler(message)`: handles "Обновить" button press
- `register_handlers(bot)`: stateless registration (no FSM, no storage wrapper)

### Wiring

- `bot/main.py`: imports debtors handler and calls `debtors.register_handlers(bot)`
- `bot/handlers/commands.py`: `/debtors - список должников` added to КОМАНДЫ help section

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 676546e | feat | add get_debtors, get_all_active_sellers, debtors_keyboard, format_debtors_list, format_reminder |
| cf0bde1 | feat | add /debtors command handler with Обновить button and registration |

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | get_debtors uses Python timedelta(days=7) | SQLite no INTERVAL support; consistent with existing datetime.utcnow() pattern throughout codebase |
| D2 | Correlated subquery for BOOKED seat count | Cleaner than GROUP BY; enables simple WHERE booked_count > 0 filter |
| D3 | /debtors and Обновить are stateless (no FSM) | Read-only view; no multi-step flow; follows commands.py pattern |
| D4 | Shared _show_debtors() private helper | Both handlers execute identical logic; extracted to avoid duplication |
| D5 | Admin (role=ADMIN) passes seller_id=None | Admin sees all; seller sees only their own per CONTEXT.md spec |
| D6 | format_reminder() takes same dict list as format_debtors_list | Cron script passes get_debtors() result directly; no transform needed |

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

Plan 02 (cron reminder script) is ready to execute. It needs:
- `get_debtors(seller_id)` - done
- `get_all_active_sellers()` - done
- `format_reminder(debtors)` - done
- VKBottle `Bot.api.messages.send` pattern documented in RESEARCH.md

---
phase: 05-debtors-reminders
plan: "02"
name: cron-reminder-script
subsystem: automation
tags: [cron, vkbottle, asyncio, audit-log, reminder, debtors]

dependency-graph:
  requires:
    - "05-01"  # get_debtors, get_all_active_sellers, format_reminder from Plan 01
    - "03-01"  # AuditLog patterns, SessionLocal, ActorType.SYSTEM
  provides:
    - "scripts/send_debtors_reminders.py standalone cron script"
    - "log_reminder_sent() audit function in bot/utils/db.py"
  affects: []

tech-stack:
  added: []
  patterns:
    - "Standalone asyncio script with sys.path.insert for project-root imports"
    - "Per-seller try/except: VKAPIError and Exception caught independently to preserve batch"
    - "Crontab TZ=Europe/Moscow header comment for deployment guidance"
    - "ActorType.SYSTEM audit log entry for automated actions"

key-files:
  created:
    - "scripts/send_debtors_reminders.py"
  modified:
    - "bot/utils/db.py"

decisions:
  - id: "D1"
    summary: "Per-seller try/except: VKAPIError and generic Exception both caught"
    rationale: "One failure must not abort the batch; both VK API errors and unexpected errors are caught and counted separately"
  - id: "D2"
    summary: "log_reminder_sent() called only after successful VK send"
    rationale: "Audit log should reflect actual sends; failed sends are not logged as sent"
  - id: "D3"
    summary: "sys.path.insert(0, project_root) + dotenv load before all imports"
    rationale: "Script runs from crontab with arbitrary cwd; path setup ensures bot.* imports resolve"
  - id: "D4"
    summary: "logger defined at module scope with fallback for non-__main__ import"
    rationale: "Script needs logger in main() at all times; else-branch covers test imports"

metrics:
  tasks-completed: 1
  tasks-total: 1
  commits: 1
  duration: "~2 minutes"
  completed: "2026-02-18"
---

# Phase 5 Plan 02: Cron Reminder Script Summary

**One-liner:** Standalone asyncio cron script sends per-seller VK debtor reminders with per-failure resilience and SYSTEM audit logging.

## What Was Built

### Cron Script (scripts/send_debtors_reminders.py)

115-line standalone async script runnable directly via crontab:

- `sys.path.insert(0, project_root)` + `load_dotenv()` before all bot imports
- `init_db()` ensures tables exist on first run
- `Bot(token=VK_BOT_TOKEN)` for VKBottle API access
- `get_all_active_sellers()` enumerates message recipients
- Per-seller loop:
  - `get_debtors(seller_id=seller.id)` — each seller sees only their own debtors
  - Empty result: increment `skipped_count`, continue
  - `format_reminder(debtors)` formats the VK message text
  - `await bot.api.messages.send(peer_id=seller.vk_user_id, ...)` sends message
  - On success: `log_reminder_sent(seller.id, len(debtors))` + increment `sent_count`
  - On `VKAPIError`: log error, increment `error_count`, **continue** (batch not aborted)
  - On generic `Exception`: log error, increment `error_count`, **continue**
- Summary log: `"Done. Sent: N, Skipped: N, Errors: N"`
- Crontab entry documented in header:
  ```
  TZ=Europe/Moscow
  0 20 */3 * * /path/to/venv/bin/python /path/to/project/scripts/send_debtors_reminders.py >> /var/log/debtors_reminders.log 2>&1
  ```

### Audit Function (bot/utils/db.py)

**`log_reminder_sent(seller_id: int, debtor_count: int)`**
- Creates `AuditLog` with:
  - `actor_type=ActorType.SYSTEM`
  - `actor_user_id=seller_id`
  - `action_type="debtors_notification_sent"`
  - `entity_type="reminder"`
  - `payload={"seller_id": seller_id, "debtor_count": debtor_count}`
- Follows established pattern: `SessionLocal` with-block, try/except/rollback, commit

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 8a38436 | feat | add cron reminder script and log_reminder_sent audit function |

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | Per-seller try/except for both VKAPIError and Exception | One failure must not abort the batch |
| D2 | log_reminder_sent() only on successful send | Audit log reflects actual sends, not attempts |
| D3 | sys.path.insert + dotenv before bot imports | Crontab runs from arbitrary cwd; path setup ensures imports resolve |
| D4 | logger defined at module scope with else-branch for import | Needed in main() at all times; else-branch covers import-time use |

## Deviations from Plan

None - plan executed exactly as written.

## Phase 5 Complete

Both plans delivered:

**Plan 01:**
- get_debtors() and get_all_active_sellers() DB functions
- format_debtors_list() and format_reminder() message formatters
- /debtors command handler (admin sees all, seller sees own)
- Обновить button refresh handler
- /debtors documented in /help

**Plan 02:**
- scripts/send_debtors_reminders.py standalone cron script
- log_reminder_sent() audit function (debtors_notification_sent)

## Next Phase Readiness

Phase 6 (Reporting) is the final planned phase. Phase 5 is fully complete with both interactive (/debtors) and automated (cron script) debtor management operational.

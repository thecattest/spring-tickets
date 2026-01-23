# External Integrations

**Analysis Date:** 2026-01-24

## APIs & External Services

**VK (VKontakte) Integration:**
- VK Bot API - Primary interface for ticket sellers (bileteers)
  - Purpose: Create/manage reservations, record payments, manage reserves, send reminders
  - SDK/Client: Not yet specified (requires VK Bot API library)
  - Auth: VK Bot token (to be stored in environment variable, not yet defined)
  - Webhook: Bot must handle forwarded messages from buyers
  - Message forwarding: Bot receives and processes forwarded VK messages to identify buyer accounts

**Hall Map Display:**
- Public web endpoint (planned)
  - Purpose: Display hall layout with seat availability (can/cannot book status only)
  - No interactive elements required
  - Data source: `layout.json` configuration file

## Data Storage

**Databases:**
- SQLite3 (current/MVP)
  - File location: `tickets.db` (project root)
  - Connection: DATABASE_URL env var (default: `sqlite:///tickets.db`)
  - Client: SQLAlchemy 2.0+ ORM
  - Foreign key support: Enabled via PRAGMA foreign_keys=ON
  - Partial indexes: Supported (3.8.0+) for unique active seat assignments

- PostgreSQL (future migration target)
  - Connection: DATABASE_URL env var (example: `postgresql+psycopg2://user:password@host:port/dbname`)
  - Client: SQLAlchemy 2.0+ ORM (models ready for migration)
  - Driver: psycopg2-binary (optional in requirements.txt)

**File Storage:**
- JSON layout file (`layout.json`)
  - Purpose: Hall schema definition (rows, seats per row, aisles)
  - Used by: Frontend rendering and backend validation
  - Scope: Single event, single venue, single configuration
  - Responsibilities: Define row/seat ranges, vertical/horizontal aisles

## Caching

**Caching:** None detected (not planned for MVP)

## Authentication & Identity

**Auth Provider:** Custom (planned)

**Implementation Approach:**
- VK OAuth/Callback for identifying ticket sellers (bileteers) - stores VK account link
- VK account identification for buyers: determined from forwarded VK message author
- Buyer verification: Checks that payment receipt (check) is from same VK account as reservation
- Admin/Seller access control: Role-based (ENUM in models: `UserRole` with admin/seller values)

**Models supporting auth:**
- `AppUser` (in `models/user.py`): System users (admin/seller with roles)
  - Optional VK account link: `vk_user_id`, `vk_profile_url` fields
  - Role field: `UserRole` enum (admin, seller)

- `VkUser` (in `models/vk_user.py`): Buyers from VK
  - `vk_user_id`: VK user ID (unique)
  - `display_name`: VK display name
  - `profile_url`: VK profile URL

## Monitoring & Observability

**Error Tracking:** None detected (not planned)

**Logs:**
- Audit trail approach (application-level logging)
- `AuditLog` table (in `models/audit.py`) - Complete logging of all state-changing operations
  - Records: actor type (user/system), actor user ID, action type, entity type, entity ID, timestamp, payload
  - Indexes: by created_at, action_type, entity (type+ID), actor_user_id
  - Payload: JSONB/JSON field with operation details
  - Supports filtering: by time period, action type, user, entity, buyer

**Reminder Notifications:**
- System-level notification logging (planned)
  - Automatic debtors list compiled nightly (time TBD): unpaid reservations 7+ days old
  - Sent to each seller for their own reservations
  - Logged as system event with recipient list

## CI/CD & Deployment

**Hosting:** Not specified (web server required)

**CI Pipeline:** None detected

**Deployment Requirements:**
- Python 3.14+ runtime
- Database (SQLite or PostgreSQL)
- VK Bot API token
- Environment configuration (DATABASE_URL, VK_BOT_TOKEN - exact var names TBD)

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` - Database connection string
  - Default (MVP): `sqlite:///tickets.db`
  - Production: PostgreSQL string

**Planned env vars (not yet documented):**
- VK Bot API token (for message handling and sending reminders)

**Secrets location:**
- Environment variables (exact mechanism not specified yet)
- Must be secured in production deployment

## Webhooks & Callbacks

**Incoming (from VK):**
- Message forwarding endpoint (planned)
  - Trigger: Seller forwards buyer message or payment receipt to bot
  - Content: Original message from buyer account (used to identify buyer)
  - Processing: Extract buyer VK ID, determine reservation, handle operation (new booking, payment, etc.)

**Outgoing (to VK):**
- Bot message responses (state-changing operations)
  - New reservation created: Confirmation message to seller with booking details
  - Payment recorded: Confirmation to seller with payment summary
  - Daily reminders: Automated message to sellers with unpaid reservations list
  - Error/validation responses: Messages to seller when validation fails
  - Seller notifications: Messages with debtors list (nightly, ~20:00 - time TBD)

**Message Content Types:**
- Forwarded buyer messages (identification)
- Payment receipts/checks (identification + attachment)
- Bot responses (text only, no attachments specified)

## VK Integration Details

**Bot Capabilities Required:**
- Receive and process forwarded messages
- Identify message author (buyer) from forwarded content
- Send text messages to sellers and buyers
- Handle conversation state/flow (seat selection, payment confirmation, etc.)
- Store message URLs and timestamps for payment references

**Payment Check Handling:**
- Seller forwards buyer's payment confirmation message (photo/document)
- Bot extracts: message author (buyer), message timestamp (payment date), message URL (reference)
- Bot stores check reference and date for audit trail
- Matches check to reservation by buyer VK account

---

*Integration audit: 2026-01-24*

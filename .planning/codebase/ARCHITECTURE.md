# Architecture

**Analysis Date:** 2026-01-24

## Pattern Overview

**Overall:** Domain-Driven Design with SQLAlchemy ORM + Bot/Web Dual Interface

**Key Characteristics:**
- Clean separation between data models and interface layers (bot, web admin)
- Event-sourced architecture through audit logging (AuditLog table)
- Single unified seat occupancy model (`SeatAssignment`) to prevent double-booking
- State machine for seat statuses (Free → Booked → Paid, or Reserved)
- Role-based access control (Admin, Seller/Ticketer)

## Layers

**Data/Domain Layer:**
- Purpose: SQLAlchemy ORM models defining business entities and constraints
- Location: `models/` directory
- Contains: Entity models (AppUser, VkUser, Reservation, SeatAssignment, Payment, Expense, ReconcileCheckpoint, AuditLog)
- Depends on: SQLAlchemy, Python standard library (datetime, enum)
- Used by: All application code (bot, web, services)

**Database Layer:**
- Purpose: Connection pooling, session management, transaction handling
- Location: `database.py`
- Contains: Engine creation, SessionLocal factory, context manager `get_session()`
- Depends on: SQLAlchemy, environment configuration
- Used by: All domain operations

**Interface Layers (Planned):**
- Bot Interface: VK bot for ticketer operations (seat booking, payment recording, reservations)
- Web Admin Interface: Financial reports, audit logs, checkpoints
- Web Public Interface: Static hall map (read-only seat availability visualization)
- Web Ticketer Page: "Concert Day" table with search and print

## Data Flow

**Reservation Creation Flow:**

1. Ticketer triggers bot with forwarded VK message from buyer
2. Bot extracts buyer VK account info → creates/finds VkUser record
3. Ticketer inputs row number → bot validates via JSON layout
4. Bot shows available seats in that row (parsed from SeatAssignment table)
5. Ticketer inputs seat list (format: "1-3,5,8-10")
6. System validates all seats exist and are free (atomically)
7. System creates SeatAssignment records with status='booked' and links to Reservation
8. AuditLog records the action with payload (seats added, who, when)

**Payment Recording Flow:**

1. Ticketer forwards payment receipt (VK message) to bot
2. Bot identifies buyer and finds their active Reservation
3. Bot asks: "How many seats paid by this receipt?"
4. System creates Payment record with vk_message_url and vk_message_ts
5. System creates PaymentSeat entries linking Payment to specific SeatAssignment records
6. System updates SeatAssignment.status from 'booked' → 'paid' (deterministic order: by row then seat)
7. Reservation.last_activity_at is updated (triggers 7-day reminder countdown)
8. AuditLog records payment with seat count and payment ID

**Financial Report Flow:**

1. Admin views Finance page
2. System aggregates:
   - SUM(paid seats) × price = revenue
   - SUM(booked seats) × price = pending
   - revenue - expenses = balance
3. System queries Expense table for outflows
4. System queries ReconcileCheckpoint to show verified-vs-new boundary

**Delinquent Reminder Flow (System):**

1. Scheduled job queries: Reservations where state='active' AND last_activity_at ≤ now()-7days AND exists unpaid seats
2. Groups results by sold_by_user_id (ticketer)
3. Sends VK message to each ticketer with their delinquent list
4. AuditLog records reminder send with system actor

## Key Abstractions

**Reservation:**
- Purpose: Represents a buyer's booking, linking VK customer to seats and ticketer
- Examples: `models/reservation.py`
- Pattern: Aggregate root for booking operations; tracks state (active/cancelled) and last activity for reminders
- Indexed by: buyer_vk_user_id, sold_by_user_id, last_activity_at

**SeatAssignment (Unified Occupancy Model):**
- Purpose: Single source of truth for seat availability status
- Examples: `models/seat_assignment.py`
- Pattern: Soft-delete via released_at timestamp; partial unique index (released_at IS NULL) prevents double-booking
- Constraints:
  - Single active assignment per seat (enforced by unique index on row_number, seat_number WHERE released_at IS NULL)
  - Coordinates validated against JSON layout (application-level)
  - Status must be one of: booked, paid, reserved
  - Foreign key CASCADE to Reservation (deleting reservation cascades to seats)

**Payment + PaymentSeat:**
- Purpose: Decouple payment records from seat-status updates; track partial payments
- Examples: `models/payment.py`
- Pattern: Payment aggregates PaymentSeat join records (M:N between Payment and SeatAssignment)
- Semantics: Each SeatAssignment can be "paid" by exactly one Payment (enforced by unique index on seat_assignment_id)

**AuditLog:**
- Purpose: Complete audit trail for compliance and debugging
- Examples: `models/audit.py`
- Pattern: Event sourcing; all state-changing operations create a log entry with actor, action_type, entity_type, entity_id, payload
- Indexed by: created_at, action_type, entity_type+entity_id, actor_user_id

**AppUser:**
- Purpose: Internal system user (ticketer or admin) with role-based access
- Examples: `models/user.py`
- Pattern: Can optionally link to VkUser if ticketer is also a VK customer

**VkUser:**
- Purpose: External buyer identity (immutable VK account reference)
- Examples: `models/vk_user.py`
- Pattern: vk_user_id is external system identifier, display_name and profile_url are cached from VK

## Entry Points

**Database Initialization:**
- Location: `database.py` (main block)
- Triggers: `python database.py` or `init_db()` call
- Responsibilities: Create all tables, indexes, and constraints from ORM models

**Bot Interface (Planned):**
- Location: (Not yet implemented; will be bot/ directory)
- Triggers: VK message forwarded to bot
- Responsibilities: Parse seat input, validate against JSON layout, execute atomic reservation/payment operations, send formatted responses

**Web Admin Interface (Planned):**
- Location: (Not yet implemented; will be web/ directory)
- Triggers: HTTP requests to /finance, /audit, /reconcile endpoints
- Responsibilities: Render financial reports, execute admin-only operations (payment reversal, expense management, checkpoint creation)

**Session Management:**
- Location: `database.py` function `get_session()`
- Pattern: Context manager; auto-commits on success, rolls back on exception
- Usage: All service operations wrap in `with get_session() as session:`

## Error Handling

**Strategy:** Transactional rollback with detailed logging to AuditLog

**Patterns:**

**Constraint Violations:**
- Double-booking attempt (seat already assigned): Caught by unique index on SeatAssignment; ORM raises IntegrityError
- Non-existent seat (row/seat not in layout): Validated application-side against JSON layout; user receives formatted error
- Invalid actor (ticketer trying admin operation): Authorization check before operation; denied with reason

**Data Consistency:**
- Foreign key violation: SQLite PRAGMA foreign_keys=ON enabled in `database.py`; cascades deletions (Reservation → SeatAssignment)
- Partial payment exceeding booked seats: Validated before PaymentSeat creation; user asked for correct number
- Atomicity: All seat additions/removals in single transaction; either all succeed or all roll back

**Audit Trail:**
- Failed operations still logged (AuditLog created before/during, with error payload if operation fails)
- Actor, timestamp, entity references logged for all actions
- Rollback does NOT remove audit entries (immutable log)

## Cross-Cutting Concerns

**Logging:**
- Database: AuditLog table with actor_type (user/system), action_type catalog (to be detailed later), payload (JSON for flexibility)
- Formatting: Ticketer receives human-readable seat ranges ("1-3,5,8-10") and confirmation sums
- SQL: Conditional echo via SQL_ECHO environment variable (database.py line 42)

**Validation:**
- Seat existence: JSON layout file (layout.json) loaded by frontend and backend
- Reservation state: Enum ReservationState in `models/base.py`; state machine transitions enforced at application level
- Partial payment: Quantity must not exceed booked seat count; system selects seats deterministically (order by row, then seat)

**Authentication (Planned):**
- VK bot: Verify sender of forwarded message matches reservation buyer (application-level check)
- Web admin: (Not yet detailed; assume OAuth/session-based)
- VK message URLs: Stored as-is; admin can verify authenticity by following link to VK chat

---

*Architecture analysis: 2026-01-24*

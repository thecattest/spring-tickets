# Architecture

**Analysis Date:** 2026-02-19

## Pattern Overview

**Overall:** Two-tier distributed application (VK Bot + Web API) sharing a common SQLAlchemy database, with Redis-based FSM state management.

**Key Characteristics:**
- **Dual interfaces:** VKBottle-based messaging bot (primary interface for sellers) + FastAPI web dashboard (secondary for admin)
- **FSM-driven bot:** Stateful conversation using Redis with full context persistence (no TTL; states survive restarts)
- **Shared data layer:** Single SQLAlchemy ORM models accessed by both bot handlers and web endpoints
- **Event-driven handlers:** Bot processes VK messages through async handler registry pattern
- **Layered isolation:** Clear separation between handlers, utilities, models, and database
- **Audit trail:** All state-changing operations logged via AuditLog table with actor, timestamp, action, entity references

## Layers

**Handler Layer (Bot):**
- Purpose: Process incoming VK messages and orchestrate state transitions
- Location: `bot/handlers/` (commands.py, reservation.py, menu.py, deletion.py, payment.py, reserve.py, debtors.py)
- Contains: Async message handlers, state machine transitions, business logic orchestration
- Depends on: FSM storage, utility layer (db.py, layout.py, messages.py), models, database
- Used by: VKBottle dispatcher

**FSM/State Management Layer:**
- Purpose: Manage conversation state and context persistence via Redis
- Location: `bot/fsm/states.py`, `bot/fsm/storage.py`
- Contains: BotState enum, RedisStorage class (ABCStateDispenser implementation)
- Depends on: redis.asyncio, vkbottle dispatch
- Used by: All handlers for get/set state operations

**Utility/Service Layer (Bot):**
- Purpose: High-level database operations, layout validation, message formatting
- Location: `bot/utils/` (db.py, layout.py, seat_parser.py, formatting.py)
- Contains: Reservation CRUD, seat availability checks, audit logging, script generation
- Depends on: Models, database session factory
- Used by: All handlers

**Message/Keyboard Layer (Bot):**
- Purpose: Template responses and UI elements
- Location: `bot/messages.py` (script/format generation), `bot/keyboards.py` (button layouts)
- Contains: Formatted text responses, keyboard JSONs for VK
- Depends on: Models, utils (formatting)
- Used by: Handlers

**Data/Domain Layer:**
- Purpose: SQLAlchemy ORM models with constraints, enums, and indexes
- Location: `models/` (base.py, user.py, vk_user.py, reservation.py, seat_assignment.py, payment.py, audit.py, reconcile.py)
- Contains: Entity classes with relationships, constraints, indexes
- Depends on: SQLAlchemy, Python stdlib (datetime, enum)
- Used by: Handlers, utilities, web endpoints

**Database Layer:**
- Purpose: Connection pooling, session management, engine initialization
- Location: `database.py`
- Contains: Engine creation (SQLite default, PostgreSQL via env), SessionLocal factory, init_db()
- Depends on: SQLAlchemy, environment variables
- Used by: All database operations

**Presentation Layer (Web):**
- Purpose: HTTP API for public hall view and admin dashboard
- Location: `web/app.py`
- Contains: FastAPI routes (GET /, GET /payments, POST /payments/login, POST /payments/checkpoint)
- Depends on: Models, database, Jinja2 templates
- Used by: HTTP clients (browsers, API consumers)

**Configuration Layer:**
- Purpose: Centralize environment and runtime configuration
- Location: `bot/config.py`
- Contains: VK token, Redis connection, database URL, seat pricing, logging setup
- Depends on: Environment variables, file system
- Used by: Bot startup, handlers, utilities

## Data Flow

**Reservation Creation Flow:**

1. Seller forwards customer message to bot → `forwarded_message_handler()` in `bot/handlers/reservation.py`
2. Handler checks FSM state: IDLE → create new reservation, MAIN_MENU → show menu or context switch
3. FSM stores buyer_vk_id, display_name, reservation_id in Redis context
4. FSM transitions to AWAITING_ROW state
5. Seller enters row number → handler validates against layout via `is_valid_row()`
6. FSM transitions to AWAITING_SEATS state
7. Seller enters seats (format "1,3,5-7") → `parse_seats()` parser validates and creates SeatAssignment records
8. Each seat creation calls `db.assign_seats()` which:
   - Queries occupied seats via `SeatAssignment.released_at IS NULL`
   - Raises `SeatOccupiedError` if conflicts found
   - Creates records with status=BOOKED, links to Reservation
   - Records audit log via `db.record_audit_log()`
9. Handler shows menu: "Добавить еще" or "Готово"
10. On "Готово", generates customer script via `generate_reservation_script()`, returns to IDLE

**Payment Recording Flow:**

1. Seller forwards receipt message (with photo/doc attachment) or presses "Оплата" button in MAIN_MENU
2. `start_payment_flow()` in `bot/handlers/payment.py` loads reservation seats via `db.get_reservation_seats()`
3. Filters BOOKED seats and shows quantity selection keyboard
4. FSM transitions to PAYMENT_QUANTITY state
5. Seller selects quantity (button "1", "2", ..., "Все 5", or "Отмена")
6. `payment_quantity_handler()` validates:
   - Quantity ≤ booked seat count
   - Amount = quantity × SEAT_PRICE (from config)
7. Creates Payment record with recorded_by_user_id, payment_amount, seat_count, vk_message_url/ts
8. Calls `db.record_payment()` which:
   - Updates selected SeatAssignment records: status BOOKED → PAID
   - Creates PaymentSeat join records (audit via unique index prevents double-pay)
   - Updates Reservation.last_activity_at (for 7-day reminder countdown)
   - Records audit log with payment_id and affected seats
9. Returns to MAIN_MENU or IDLE

**Web Hall View Flow:**

1. User navigates to `GET /` → `hall()` endpoint in `web/app.py`
2. Loads cached layout from `bot/utils/layout.py` (global _layout_cache)
3. Queries occupied seats: `SELECT row_number, seat_number FROM seat_assignments WHERE released_at IS NULL`
4. Renders hall.html template with seat grid and CSS occupancy classes
5. Shows stats: total_seats, total_occupied, total_free

**Web Payments Dashboard Flow:**

1. User navigates to `GET /payments` → `payments_page()` endpoint
2. Checks authentication via cookie with URLSafeTimedSerializer (24hr TTL)
3. If not authenticated, redirects to `GET /payments/login`
4. On `POST /payments/login`, validates password against PAYMENTS_PASSWORD env var
5. Payments page aggregates:
   - All Payment records with JOINs to VkUser (buyer), AppUser (seller)
   - ReconcileCheckpoint records (checkpoints group payments into periods)
   - SeatAssignment counts grouped by status
   - Money stats: total_paid, projected (booked × SEAT_PRICE)
6. Renders payments.html with sections:
   - Current (payments after latest checkpoint)
   - Historical sections per checkpoint
   - Seat and money stats
7. Admin can `POST /payments/checkpoint` to create ReconcileCheckpoint

**State Persistence in Redis:**

- Key pattern: `bot:fsm:{peer_id}` (peer_id = seller's VK user ID)
- Value: JSON serialized StatePeer object
  ```
  {
    "peer_id": 12345,
    "state": "main_menu",
    "payload": {
      "reservation_id": 42,
      "buyer_vk_user_id": 99,
      "buyer_vk_api_id": 999,
      "buyer_display_name": "John Doe",
      "flow_specific_field": "value"
    }
  }
  ```
- No TTL: persists until explicitly cleared (via cancel or new context switch)
- Retrieved via `storage.get(peer_id)` → StatePeer or `storage.get_context(peer_id)` → payload dict

## Key Abstractions

**Reservation:**
- Purpose: Groups seats purchased by a single customer under one sale transaction
- Location: `models/reservation.py`
- Fields: buyer_vk_user_id (FK), sold_by_user_id (FK), state (ACTIVE/CANCELLED), created_at, last_activity_at
- Pattern: One-to-many with SeatAssignment via FK; aggregate root for booking operations
- Indexes: buyer_idx, sold_by_idx, last_activity_idx

**SeatAssignment:**
- Purpose: Unified table tracking all seat occupancy (booked/paid/reserved/free)
- Location: `models/seat_assignment.py`
- Key fields: row_number, seat_number, status (BOOKED/PAID/RESERVED), reservation_id (nullable), released_at (nullable)
- Pattern: Soft-delete via released_at; unique active constraint per seat (partial unique index WHERE released_at IS NULL)
- Semantics:
  - BOOKED: linked to reservation, not yet paid
  - PAID: linked to reservation, payment recorded
  - RESERVED: admin reserve (no reservation_id)
- Used by: Hall view (occupied check), payment flow (seat status), availability checks

**Payment:**
- Purpose: Record cash/transfer receipt amount and associate with seats
- Location: `models/payment.py`
- Fields: reservation_id, seat_count, payment_amount (Decimal), recorded_by_user_id, vk_message_url, vk_message_ts
- Relationships: Belongs to Reservation; has many SeatAssignment via PaymentSeat join table
- Pattern: Tracks partial payments (one receipt may cover N of M booked seats)

**PaymentSeat:**
- Purpose: Join table linking Payment to specific SeatAssignment records
- Location: `models/payment.py`
- Unique constraint: seat_assignment_id (prevents double-paying a seat)

**VkUser:**
- Purpose: External VK user identity (customer/buyer)
- Location: `models/vk_user.py`
- Fields: vk_user_id (external VK API ID), display_name, updated_at
- Pattern: Get-or-create on first message from customer via `db.get_or_create_vk_user()`

**AppUser:**
- Purpose: Internal app user (seller/admin with role)
- Location: `models/user.py`
- Fields: role (ADMIN/SELLER), display_name, vk_user_id (optional, links to VkUser), is_active
- Pattern: Seller is AppUser + can be VkUser if also a buyer

**Layout:**
- Purpose: Define hall geometry and seat counts per row
- Location: `layout.json` (root), cached in `bot/utils/layout.py` (_layout_cache global)
- Structure: JSON with "rows" dict: `{"1": {"seatCount": 28}, "2": {"seatCount": 28}, ...}`
- Also contains: "layout" key with "verticalAisles" for rendering aisles on web view
- Pattern: Loaded once at bot startup; used for seat validation (is_valid_seat, is_valid_row, get_seat_count)

**BotState:**
- Purpose: FSM state enum defining conversation flows
- Location: `bot/fsm/states.py`
- States: IDLE, AWAITING_ROW, AWAITING_SEATS, SEAT_ADDITION_MENU, MAIN_MENU, DELETING_ROW, DELETING_SEATS, DELETION_CONFIRM, CANCEL_CONFIRM, CONTEXT_SWITCH_CONFIRM, PAYMENT_QUANTITY, RESERVE_* (6 reserve states)
- Pattern: Flows documented as state transition diagrams in docstring

**RedisStorage:**
- Purpose: Persistent FSM state dispenser using Redis
- Location: `bot/fsm/storage.py`
- Methods: `async get(peer_id)`, `async set(peer_id, state, **kwargs)`, `async clear(peer_id)`, `async get_context(peer_id)`
- Pattern: Implements ABCStateDispenser; StatePeer serialized to JSON

## Entry Points

**Bot Entry Point:**
- Location: `bot/main.py`, `bot/__main__.py`
- Triggers: `python bot/main.py` or `python -m bot`
- Responsibilities:
  1. Setup logging from LOG_LEVEL env var
  2. Validate configuration (VK_BOT_TOKEN, VK_GROUP_ID, layout file exists)
  3. Initialize Redis FSM storage (connect, test ping)
  4. Register 7 handler groups: commands, reservation, menu, deletion, payment, reserve, debtors
  5. Initialize database (create tables)
  6. Load layout.json into cache
  7. Start polling VK API: `bot.run_forever()`

**Web Entry Point:**
- Location: `web/app.py`
- Triggers: `uvicorn web.app:app --host 0.0.0.0 --port 5000`
- Responsibilities:
  1. Serve public endpoints: `GET /`, `GET /payments/login`, `POST /payments/login`
  2. Serve admin endpoints: `GET /payments`, `POST /payments/checkpoint` (auth required)
  3. Load session per request (no caching); commit on success
  4. Render Jinja2 templates

**Scripts:**
- Location: `scripts/send_debtors_reminders.py`
- Triggers: Manual invocation or cron
- Responsibilities: Query overdue reservations, send reminders to sellers

**Database Initialization:**
- Location: `database.py`
- Triggers: `python database.py` or called by bot/web startup
- Responsibilities: Create all tables, indexes, constraints

## Error Handling

**Strategy:** Multi-layer validation with custom exception hierarchy

**Custom Exceptions** (`bot/utils/db.py`):
- `DatabaseError`: Base exception for all DB operations
- `PermissionError(DatabaseError)`: User lacks permission for operation
- `SeatOccupiedError(DatabaseError)`: Attempted to assign already-occupied seats; includes conflict list with row/seat/status/note/reservation_id
- `InsufficientSeatsError(DatabaseError)`: Payment quantity exceeds available BOOKED seats

**Handler Pattern:**
```python
try:
    result = db.assign_seats(...)
except db.SeatOccupiedError as e:
    await message.answer(f"Места заняты:\n{format_conflicts(e.conflicts)}")
except db.DatabaseError as e:
    logger.error(f"DB error: {e}")
    await message.answer("Ошибка. Попробуйте позже.")
```

**Layout Validation:**
- Custom exception: `LayoutError` in `bot/utils/layout.py`
- Raised: During bot startup if layout.json missing, invalid JSON, or schema mismatch
- Effect: Bot refuses to start; prevents runtime failures during seat validation

**Database Constraints:**
- Foreign keys: PRAGMA foreign_keys=ON enabled globally in database.py
- SeatAssignment: Unique (row_number, seat_number) WHERE released_at IS NULL (prevents double-booking)
- PaymentSeat: Unique seat_assignment_id (prevents double-paying)
- Reservation: Checked via last_activity_at for 7-day reminder logic
- Check constraints: row_number BETWEEN 1-24, seat_number BETWEEN 1-28

**Atomicity:**
- All multi-row operations wrapped in single transaction
- Example: assigning 3 seats either all succeed or all rollback
- Handled by SQLAlchemy session commit/rollback

## Cross-Cutting Concerns

**Logging:**
- Framework: Python logging module (stdlib)
- Configuration: `bot/config.py` setup_logging() reads LOG_LEVEL env var
- Pattern: All modules use `logger = logging.getLogger(__name__)`
- Suppression: aiohttp and vkbottle loggers set to WARNING
- Audit: Separate from application logs; stored in AuditLog table (complete event trail)

**Validation:**
- **Seats:** Layout-based per `bot/utils/layout.py` (is_valid_row, is_valid_seat, get_seat_count)
- **Sellers:** Role check (ADMIN vs SELLER) in reserve handler
- **Payments:** Amount = quantity × SEAT_PRICE enforced before Payment creation
- **Input parsing:** Seat parser in `bot/utils/seat_parser.py` handles "1-5, 10" notation with SeatParseError exception

**Authentication:**
- **Bot:** VK token validates message origin via VKBottle framework (built-in)
- **Web dashboard:** URLSafeTimedSerializer cookie with 24hr TTL via COOKIE_MAX_AGE
- **Role-based:** ADMIN vs SELLER enforced in reserve operations (admin-only feature)

**Audit Trail:**
- Table: `models/audit.py` (AuditLog)
- Recorded: Seat assignments, updates, deletions, payments, context switches
- Called by: `db.record_audit_log()` after every state-changing DB operation
- Fields: actor_type (USER/SYSTEM), actor_id, action, target_type, target_id, created_at, details (JSON)
- Immutable: Rollback does NOT delete audit entries (event source of truth)

---

*Architecture analysis: 2026-02-19*

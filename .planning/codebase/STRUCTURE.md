# Codebase Structure

**Analysis Date:** 2026-02-19

## Directory Layout

```
Tickets/
├── .planning/                      # GSD planning documentation
│   ├── config.json                # GSD workflow config
│   └── codebase/                  # Generated architecture docs (STACK.md, ARCHITECTURE.md, etc.)
├── bot/                           # VK Bot implementation
│   ├── __init__.py               # Package marker + version
│   ├── __main__.py               # Entry point for `python -m bot`
│   ├── main.py                   # Bot setup and polling loop
│   ├── config.py                 # Configuration (VK token, Redis, DB, logging)
│   ├── keyboards.py              # Keyboard JSON generators
│   ├── messages.py               # Response templates and script generation
│   ├── fsm/                      # Finite State Machine
│   │   ├── __init__.py
│   │   ├── states.py             # BotState enum (IDLE, AWAITING_ROW, MAIN_MENU, etc.)
│   │   └── storage.py            # RedisStorage: Redis-backed FSM state dispenser
│   ├── handlers/                 # Message handlers (async functions)
│   │   ├── __init__.py           # Handler registration
│   │   ├── commands.py           # /start, /help, /cancel handlers
│   │   ├── reservation.py        # Forwarded message, row/seat input handlers
│   │   ├── menu.py               # Main menu display and button handlers
│   │   ├── deletion.py           # Seat deletion and deletion flow
│   │   ├── payment.py            # Payment recording and quantity selection
│   │   ├── reserve.py            # Admin reserve management (ADMIN-only)
│   │   └── debtors.py            # Debtor reminder handlers
│   ├── utils/                    # High-level utility functions
│   │   ├── __init__.py
│   │   ├── db.py                 # Database operations (CRUD, audit)
│   │   ├── layout.py             # Hall layout loading and validation
│   │   ├── seat_parser.py        # Seat input parser (format: "1-5,10,12-15")
│   │   └── formatting.py         # Seat range formatting (1-5,10 to text)
│   └── tests/                    # Bot integration tests
│       ├── __init__.py
│       ├── test_db_integration.py
│       ├── test_redis_fsm.py
│       └── test_seat_parser.py
├── models/                       # SQLAlchemy ORM models
│   ├── __init__.py              # Model exports
│   ├── base.py                  # Base class + ENUM types (UserRole, SeatStatus, etc.)
│   ├── user.py                  # AppUser (internal system user)
│   ├── vk_user.py               # VkUser (external VK customer)
│   ├── reservation.py           # Reservation (booking aggregate)
│   ├── seat_assignment.py       # SeatAssignment (unified occupancy table)
│   ├── payment.py               # Payment + PaymentSeat (join table)
│   ├── audit.py                 # AuditLog (event trail)
│   └── reconcile.py             # ReconcileCheckpoint (financial checkpoints)
├── web/                         # FastAPI web interface
│   ├── app.py                   # FastAPI routes (hall, payments, auth)
│   └── templates/               # Jinja2 templates
│       ├── hall.html            # Public hall map
│       ├── payments.html        # Admin payments dashboard
│       └── payments_login.html  # Auth form
├── scripts/                     # Standalone scripts
│   └── send_debtors_reminders.py # Scheduled debt reminder job
├── database.py                  # Engine, session factory, init_db()
├── layout.json                  # Hall layout (rows, seat counts, aisles)
├── tickets.db                   # SQLite database (MVP, generated)
├── requirements.txt             # Python dependencies
├── test_db.py                   # Database initialization test
├── .env.example                 # Example environment variables
├── .gitignore                   # Git ignore rules
├── CLAUDE.md                    # Claude-specific notes
├── DB_SCHEMA.md                 # Detailed schema documentation
├── README_MODELS.md             # SQLAlchemy usage guide
├── SQLITE_MIGRATION.md          # Migration guide
├── TZ.md                        # Full technical specification (Russian)
└── .git/                        # Version control
```

## Directory Purposes

**bot/:**
- Purpose: VK bot implementation for seller-side interface
- Contains: Stateful message handlers, FSM storage, utilities, keyboards, messages
- Key patterns: Async handlers, FSM state transitions, context persistence in Redis

**models/:**
- Purpose: Domain model layer (SQLAlchemy ORM)
- Contains: Entity classes with table definitions, indexes, constraints, ENUMs
- Key files: `base.py` (foundation), individual model files (one per entity)

**web/:**
- Purpose: FastAPI web interface for public hall view and admin dashboard
- Contains: HTTP routes, Jinja2 templates, authentication
- Key files: `app.py` (all routes in one file)

**bot/fsm/:**
- Purpose: Conversation state management
- Contains: BotState enum, RedisStorage class
- Key pattern: StatePeer serialized to JSON in Redis

**bot/handlers/:**
- Purpose: Async message handlers for different conversation flows
- Contains: One handler file per flow (reservation, menu, payment, deletion, etc.)
- Key pattern: Each handler registered in `handlers/__init__.py` and called from `main.py`

**bot/utils/:**
- Purpose: High-level database operations and validation
- Contains: DB CRUD functions, seat validation, message formatting
- Key pattern: db.py is largest file; single responsibility for database operations

**scripts/:**
- Purpose: Standalone background jobs
- Contains: Debt reminder script, future: cleanup, reconciliation

## Key File Locations

**Entry Points:**
- Bot: `bot/main.py` (or `python -m bot`)
- Web: `web/app.py` (run via uvicorn)
- DB init: `database.py` (or called automatically)

**Configuration:**
- Environment: `bot/config.py` (reads .env, validates)
- Layout: `layout.json` (JSON, loaded once at startup)
- Database: `database.py` (engine, URL from env)

**Core Business Logic:**
- Database operations: `bot/utils/db.py` (largest file: ~1000 lines)
- Seat validation: `bot/utils/layout.py`
- Message handlers: `bot/handlers/*.py`
- Models: `models/*.py` (constraints, indexes, relationships)

**Presentation:**
- Bot responses: `bot/messages.py` (script generation, formatting)
- Bot UI: `bot/keyboards.py` (button layouts)
- Web templates: `web/templates/*.html` (Jinja2)

**Testing:**
- Bot tests: `bot/tests/*.py`
- DB test: `test_db.py`

## Naming Conventions

**Files:**
- Model files: `snake_case.py` matching entity (e.g., `seat_assignment.py` → `SeatAssignment`)
- Handler files: `{flow}.py` (e.g., `payment.py`, `deletion.py`)
- Test files: `test_*.py`
- Config files: `config.py`, `settings.py`
- Template files: `{entity}.html` (e.g., `hall.html`, `payments.html`)

**Python:**
- Classes: `PascalCase` (SeatAssignment, RedisStorage, BotState)
- Functions/methods: `snake_case` (get_reservation_seats, assign_seats)
- Constants: `UPPER_CASE` (SEAT_PRICE, VK_BOT_TOKEN)
- ENUMs: `PascalCase` with `UPPER_CASE` values (UserRole.ADMIN, SeatStatus.BOOKED)
- Private functions: `_snake_case` (e.g., `_make_key` in RedisStorage)

**Database:**
- Tables: `snake_case` plural (app_users, reservations, seat_assignments)
- Columns: `snake_case` (vk_user_id, created_at, released_at)
- Indexes: `{table}_{columns}_idx` or `{table}_{purpose}` (e.g., seat_assignments_one_active_per_seat)
- Foreign keys: `{target_table}_id` (e.g., buyer_vk_user_id references vk_users.id)

**VK/Web:**
- Buttons: CyrilicCase (e.g., "Добавить еще", "Готово")
- Routes: `/kebab-case` (e.g., `/payments/login`, `/payments/checkpoint`)
- Cookie: `snake_case` (payments_auth)

## Where to Add New Code

**New Handler (Bot):**
1. Create file: `bot/handlers/{flow_name}.py`
2. Define async handler function: `async def {action}_handler(message: Message, storage: RedisStorage):`
3. Register in `bot/handlers/__init__.py`: `from . import {flow_name}` and add to imports
4. Register in `bot/main.py`: `{flow_name}.register_handlers(bot)`
5. Define state(s) in `bot/fsm/states.py` if needed
6. Use `bot/utils/db.py` for database operations
7. Use `bot/messages.py` for formatted responses
8. Use `bot/keyboards.py` for UI elements

**New Model:**
1. Create file: `models/{entity_name}.py`
2. Import in: `models/__init__.py` (add to imports and __all__)
3. Define class:
   - Inherit from `Base`
   - Set `__tablename__ = "snake_case_name"`
   - Define Mapped columns with type annotations
   - Add indexes/constraints in `__table_args__`
   - Define `__repr__` for debugging
4. Example to follow: `models/seat_assignment.py` (most complex with partial indexes)

**New Web Route:**
1. Add function to `web/app.py`:
   - Use `@app.get("/path")` or `@app.post("/path")`
   - Parameter: `request: Request`
   - Use `SessionLocal()` context manager
   - Return `TemplateResponse` or `RedirectResponse`
2. Create template in `web/templates/{entity}.html` if needed
3. Authentication check: Use `is_authenticated(request)` helper

**New Database Operation:**
1. Add function to `bot/utils/db.py`:
   - Pattern: Open SessionLocal, execute query, close on exit
   - Return: Model instances or primitives
   - Raise: Custom DatabaseError subclass on failure
   - Call: `record_audit_log()` after state-changing operations
2. If complex, add helper in separate file under `bot/utils/`

**New Background Script:**
1. Create file: `scripts/{job_name}.py`
2. Define main function: `def main():`
3. Use `SessionLocal()` for database access
4. Can be invoked via cron or CLI
5. Example: `scripts/send_debtors_reminders.py`

**New Test:**
1. Create in `bot/tests/` for bot-specific tests
2. Use `pytest` framework
3. Import from `models`, `bot.utils.db`, etc.
4. Use fixtures for SessionLocal, Redis storage

## Special Directories

**`.planning/`:**
- Purpose: GSD (Generative Specification Document) workflow
- Contents: Architecture docs (STACK.md, ARCHITECTURE.md, STRUCTURE.md, TESTING.md, CONVENTIONS.md, CONCERNS.md, INTEGRATIONS.md)
- Committed: Yes

**`.git/`:**
- Purpose: Version control
- Committed: Yes

**`web/templates/`:**
- Purpose: Jinja2 template files for web interface
- Files: hall.html (public), payments.html (admin), payments_login.html (auth form)
- Context: Each route passes dict to TemplateResponse

**`migrations/`:**
- Purpose: Database migration scripts (future use)
- Current: Empty; schema managed by SQLAlchemy models
- Usage: When migrating SQLite → PostgreSQL

**`__pycache__/`, `.pytest_cache/`:**
- Purpose: Generated caches (Python bytecode, pytest)
- Generated: Yes (by Python/pytest)
- Committed: No (in .gitignore)

**`tickets.db`:**
- Purpose: SQLite database file (MVP only)
- Generated: Yes (by SQLAlchemy on init_db())
- Committed: No (should be .gitignore)
- Production: Replace with PostgreSQL via DATABASE_URL env var

## Key Files to Know

**`bot/config.py` (97 lines):**
- Loads configuration from environment
- Sets up logging
- Validates required config (VK token, layout file)
- Used by: All bot modules

**`bot/main.py` (110 lines):**
- Entry point for bot
- Initializes Redis, database, layout
- Registers all handlers
- Starts polling loop

**`bot/utils/db.py` (~1000 lines):**
- Largest file in codebase
- All database CRUD operations
- Custom exception classes
- Audit logging
- Seat assignment logic

**`database.py` (68 lines):**
- Session factory and engine creation
- init_db() function
- SQLite foreign key enablement

**`models/base.py` (40 lines):**
- Base class for all models
- ENUM types (UserRole, ReservationState, SeatStatus, ActorType)

**`models/seat_assignment.py` (94 lines):**
- Most complex model
- Partial unique index to prevent double-booking
- Soft-delete via released_at

**`bot/fsm/storage.py` (~150 lines):**
- Redis-based state dispenser
- Implements ABCStateDispenser
- Handles StatePeer serialization

**`web/app.py` (323 lines):**
- All web routes in one file
- Hall view, payments dashboard, auth
- Uses SessionLocal per request

## Data Model Overview

**Core Entities:**
- `AppUser` (seller/admin internal)
- `VkUser` (customer external)
- `Reservation` (booking, links buyer to seller)
- `SeatAssignment` (occupancy, unified table)
- `Payment` (receipt, amount paid)
- `AuditLog` (event trail)

**Relationships:**
- Reservation.buyer_vk_user_id → VkUser.id
- Reservation.sold_by_user_id → AppUser.id
- SeatAssignment.reservation_id → Reservation.id (CASCADE)
- SeatAssignment.created_by_user_id → AppUser.id
- Payment.reservation_id → Reservation.id
- Payment.recorded_by_user_id → AppUser.id
- PaymentSeat.payment_id → Payment.id (CASCADE)
- PaymentSeat.seat_assignment_id → SeatAssignment.id

**Key Constraints:**
- SeatAssignment: Unique (row_number, seat_number) WHERE released_at IS NULL
- PaymentSeat: Unique seat_assignment_id
- Reservation: Indexed by buyer, seller, last_activity
- Layout: JSON with rows and seat counts

---

*Structure analysis: 2026-02-19*

# Codebase Structure

**Analysis Date:** 2026-01-24

## Directory Layout

```
Tickets/
├── .planning/               # GSD planning documentation
│   ├── config.json         # GSD workflow configuration
│   └── codebase/          # Generated architecture docs
├── models/                 # SQLAlchemy ORM models
│   ├── __init__.py        # Model exports
│   ├── base.py            # Base class and ENUM types
│   ├── user.py            # AppUser model
│   ├── vk_user.py         # VkUser model
│   ├── reservation.py     # Reservation model
│   ├── seat_assignment.py # SeatAssignment model (unified occupancy)
│   ├── payment.py         # Payment and PaymentSeat models
│   ├── expense.py         # Expense model
│   ├── reconcile.py       # ReconcileCheckpoint model
│   └── audit.py           # AuditLog model
├── database.py            # Engine, session factory, init
├── test_db.py             # Database integration tests
├── tickets.db             # SQLite database file (MVP)
├── requirements.txt       # Python dependencies
├── README_MODELS.md       # SQLAlchemy usage guide
├── DB_SCHEMA.md          # Detailed schema with SQL and query examples
├── SQLITE_MIGRATION.md   # SQLite to PostgreSQL migration path
├── TZ.md                 # Technical requirements (Russian)
└── TZ.md                 # Full specification with operations, flows, UI

```

## Directory Purposes

**models/:**
- Purpose: Domain model layer (SQLAlchemy ORM)
- Contains: Entity classes with table definitions, indexes, constraints, ENUMs
- Key files: `base.py` (foundation), individual model files (one per entity)

**database.py:**
- Purpose: Database connectivity and transaction management
- Contains: Engine creation (SQLite default), SessionLocal factory, get_session context manager
- Key configs: DATABASE_URL from env (defaults to sqlite:///tickets.db), SQL_ECHO for debugging

**Documentation (markdown):**
- Purpose: Requirements, schema design, and implementation guides
- Key files:
  - `TZ.md`: Complete technical specification (38KB, operations, flows, role matrix, UI mockups)
  - `DB_SCHEMA.md`: Entity relationship diagram (logical/SQL), examples, design decisions
  - `README_MODELS.md`: SQLAlchemy usage patterns, session examples, common queries
  - `SQLITE_MIGRATION.md`: MVP→production migration guide

## Key File Locations

**Entry Points:**
- `database.py`: Run with `python database.py` to initialize DB
- `models/__init__.py`: Imports all public models for `from models import *`
- No main application entry point yet (bot/web layers not implemented)

**Configuration:**
- `database.py` (lines 32-36): DATABASE_URL environment variable
- `database.py` (line 42): SQL_ECHO environment variable for query logging
- No config files (.env, .json) yet (kept to code only)

**Core Logic:**
- `models/`: All business rules encoded in constraints (CHECK, UNIQUE, FK), indexes, and ENUM definitions
- `models/base.py`: ENUM types (UserRole, ReservationState, SeatStatus, ActorType)
- `models/seat_assignment.py`: Unified seat occupancy logic with partial unique index (released_at IS NULL)
- `models/reservation.py`: Booking aggregate with last_activity_at for 7-day reminders

**Testing:**
- `test_db.py`: Integration tests demonstrating model usage (creation, updates, queries, cascades)
- No unit test framework configured yet (no pytest.ini or conftest.py)

## Naming Conventions

**Files:**
- Model files: `snake_case.py` matching entity name (e.g., `seat_assignment.py` for `SeatAssignment` class)
- Test files: `test_*.py` (only test_db.py currently)
- Documentation: `UPPERCASE.md` for technical docs (DB_SCHEMA.md, TZ.md, README_MODELS.md)

**Classes:**
- Domain models: `PascalCase` matching table purpose (e.g., `SeatAssignment`)
- ENUM types in base.py: `PascalCase` with values in `UPPER_CASE` (e.g., `UserRole.ADMIN`)

**Database Tables:**
- Snake_case (SQLAlchemy convention): `app_users`, `vk_users`, `reservations`, `seat_assignments`, `payments`, `payment_seats`, `expenses`, `reconcile_checkpoints`, `audit_log`

**Columns:**
- Snake_case: `vk_user_id`, `sold_by_user_id`, `created_at`, `released_at`, `last_activity_at`, `vk_message_ts`

**Indexes:**
- Format: `{table}_{column(s)}_idx` or `{table}_{columns}_{purpose}` (e.g., `reservations_buyer_idx`, `seat_assignments_one_active_per_seat`)

## Where to Add New Code

**New Model/Entity:**
- Create file: `models/{entity_name}.py`
- Import in: `models/__init__.py` (add to imports and __all__)
- Define:
  - Class inheriting `Base`
  - `__tablename__ = "snake_case_name"`
  - Mapped columns with type annotations
  - Indexes/constraints in `__table_args__`
  - `__repr__` for debugging
- Example to follow: `models/seat_assignment.py` (most complex with partial indexes)

**New Query/Operation:**
- Not yet structured (no service/query layer exists)
- Will likely live in `services/` directory when created
- Should use `from database import get_session` and models from `models/__init__.py`
- Must create AuditLog entry for all state-changing operations

**New Interface (Bot/Web):**
- Create directory: `bot/` or `web/`
- Depend on: `database`, `models`, and any service layer
- Each interface layer should:
  - Import models and session factory
  - Use `with get_session() as session:` for all DB operations
  - Create AuditLog entries with action_type and payload
  - Validate inputs against JSON layout for seats

**Utilities:**
- Shared helpers: `utils/` directory (not yet created)
- Examples: seat list parser (`parse_seats("1-3,5,8-10")`), availability query builders, audit log factory functions

## Special Directories

**`.planning/`:**
- Purpose: GSD (Generative Specification Document) workflow directory
- Generated: By GSD orchestrator; contains architecture docs
- Committed: Yes (docs are source of truth for future development)

**`.git/`:**
- Purpose: Version control
- Committed: Yes

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (via `python -m venv .venv`)
- Committed: No (should be in .gitignore)

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes (by Python interpreter)
- Committed: No

**`tickets.db`:**
- Purpose: SQLite database file for MVP
- Generated: Yes (by SQLAlchemy on first init_db() call)
- Committed: No (should be in .gitignore; DB schema defined by models only)

## Future Structure (Planned)

Based on TZ.md requirements, anticipated additions:

```
Tickets/
├── layout.json          # Hall seat layout (rows, seat counts, aisles)
├── config/              # Configuration management
│   └── settings.py     # Database URL, API endpoints, secrets
├── bot/                 # VK bot implementation (Planned)
│   ├── __init__.py
│   ├── client.py       # VK API client wrapper
│   ├── handlers.py     # Message handlers (reservation, payment, etc.)
│   ├── parsers.py      # Seat input parser (1-3,5,8-10 format)
│   └── formatters.py   # Response formatting
├── web/                 # Web admin interface (Planned)
│   ├── __init__.py
│   ├── api.py          # Flask/FastAPI endpoints
│   ├── auth.py         # Authentication middleware
│   └── templates/      # Jinja2 templates
├── services/            # Business logic layer (Planned)
│   ├── __init__.py
│   ├── reservation.py  # Booking operations
│   ├── payment.py      # Payment recording
│   ├── audit.py        # Audit log helpers
│   └── reminders.py    # Delinquent reminder scheduling
├── utils/               # Utilities (Planned)
│   ├── __init__.py
│   ├── seat_parser.py  # Parse "1-3,5,8-10" format
│   ├── layout.py       # Load and validate JSON layout
│   └── formatting.py   # Seat range formatting
└── tests/               # Test suite (Planned)
    ├── conftest.py     # Pytest fixtures
    ├── unit/           # Unit tests
    └── integration/    # Integration tests
```

---

*Structure analysis: 2026-01-24*

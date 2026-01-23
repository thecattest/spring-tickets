# Technology Stack

**Analysis Date:** 2026-01-24

## Languages

**Primary:**
- Python 3.14+ - Backend ORM models, database layer, API endpoints (planned)

**Secondary:**
- HTML/CSS/JavaScript - Web frontend for event day, hall map display, admin dashboards (planned)

## Runtime

**Environment:**
- Python 3.14+ (venv-based)

**Package Manager:**
- pip

**Lockfile:**
- Not detected (requirements.txt used for dependency specification)

## Frameworks

**Core:**
- SQLAlchemy 2.0+ - ORM for database models and queries
  - Location: `requirements.txt` specifies `sqlalchemy>=2.0.0`
  - Database abstraction layer in `database.py`

**API/Web:**
- Web framework not yet selected (planned for backend API)
- VK Bot API integration planned (no SDK specified yet)

**Testing:**
- Not detected in planned stack

**Build/Dev:**
- Not specified in planning documents

## Key Dependencies

**Critical:**
- SQLAlchemy (>=2.0.0) - ORM models and database operations
  - Why: Core to data persistence and model management; facilitates potential migration from SQLite to PostgreSQL

**Optional (commented in requirements.txt):**
- psycopg2-binary (>=2.9.0) - PostgreSQL driver (for future migration)
- aiosqlite (>=0.19.0) - Async SQLite support (for future async operations)
- asyncpg (>=0.29.0) - Async PostgreSQL support (for future async operations)

## Configuration

**Environment:**
- DATABASE_URL environment variable (required)
  - Default: `sqlite:///tickets.db` (SQLite file in project root)
  - Alternative: PostgreSQL connection string (future)
  - Example: `postgresql+psycopg2://user:password@host:port/dbname`

**Build:**
- `database.py` - Database initialization and session management
  - Includes PRAGMA foreign_keys=ON for SQLite cascade deletes
  - Support for both SQLite and PostgreSQL (dialect detection)

**Layout Configuration:**
- `layout.json` (planned) - Hall seat configuration
  - Used by both frontend (rendering) and backend (validation)
  - Specifies row counts, seat counts per row, aisles/passages
  - Source of truth for venue constraints

## Database

**Current (MVP):**
- SQLite3 (built-in to Python, no additional driver required)
  - File: `tickets.db` (in project root)
  - Connection string format: `sqlite:///tickets.db`
  - Supports partial indexes (SQLite 3.8.0+) for unique constraints

**Future Migration Target:**
- PostgreSQL
  - psycopg2-binary driver ready to be installed
  - All SQLAlchemy models prepared for migration
  - Changes required: ENUM type declarations, index `sqlite_where` → `postgresql_where`, optional BigInteger support

## Platform Requirements

**Development:**
- Python 3.14+
- pip package manager
- Virtual environment (venv)
- SQLite3 (built into Python)

**Production:**
- Python 3.14+
- Database: SQLite3 or PostgreSQL (configured via DATABASE_URL)
- Web server (not yet specified; will host web frontend and API endpoints)
- VK Bot API connectivity (outbound HTTPS for bot commands and webhooks)

## Session Management

**Database Sessions:**
- SQLAlchemy session factory (`SessionLocal`) configured in `database.py`
- Context manager pattern recommended: `with get_session() as session:`
- Manual session management also supported with try/finally/close pattern
- Auto-commit on context exit

---

*Stack analysis: 2026-01-24*

# Coding Conventions

**Analysis Date:** 2026-01-24

## Naming Patterns

**Files:**
- Snake_case for all Python files (e.g., `database.py`, `seat_assignment.py`, `vk_user.py`)
- Model files: singular form with descriptive name (e.g., `user.py`, `reservation.py`, `audit.py`)
- Base/common files: `base.py`, `__init__.py`

**Functions:**
- Snake_case for function names (e.g., `get_session()`, `init_db()`, `create_all()`)
- Context managers: descriptive names reflecting purpose (e.g., `get_session()`)

**Variables:**
- Snake_case for all variables and parameters (e.g., `buyer_vk_user_id`, `seat_number`, `display_name`)
- Foreign key fields follow pattern: `{entity}_{entity_id}` (e.g., `buyer_vk_user_id`, `sold_by_user_id`, `recorded_by_user_id`)
- Datetime fields: `created_at`, `updated_at`, `last_activity_at`, `cancelled_at`, `occurred_at`, `checked_at`, `released_at`
- Action fields: `created_by_user_id`, `recorded_by_user_id`, `checked_by_user_id`, `released_by_user_id`

**Classes:**
- PascalCase for all class names
- ENUM classes: `UserRole`, `ReservationState`, `SeatStatus`, `ActorType`
- Model classes: descriptive singular form (e.g., `AppUser`, `VkUser`, `Reservation`, `SeatAssignment`)

**Constants:**
- UPPER_CASE for ENUM enum values (e.g., `ACTIVE = "active"`, `ADMIN = "admin"`)

## Code Style

**Formatting:**
- Python 3.9+ syntax with type hints (PEP 484)
- Line length: no explicit limit observed; follows Python conventions
- Indentation: 4 spaces (implicit Python standard)

**Linting:**
- No explicit linting tools detected (no .eslintrc, .pylintrc, pyproject.toml)
- Code follows implicit style conventions observed in existing modules

**Type Hints:**
- Mandatory on function signatures and class attributes
- Use `Optional[T]` for nullable types (from `typing` module)
- Use `Mapped[T]` for SQLAlchemy ORM attribute declarations
- Import types explicitly (e.g., `from typing import Optional`)

## Import Organization

**Order:**
1. Standard library imports (e.g., `from datetime import datetime`, `import enum`, `import os`)
2. Third-party imports (e.g., `from sqlalchemy import ...`, `from sqlalchemy.orm import ...`)
3. Relative imports from project (e.g., `from models.base import ...`, `from database import ...`)

**Path Aliases:**
- Relative imports use explicit paths from project root: `from models.base import ...` not `from .base import ...`
- No path aliases configured; absolute imports from root

**Import Style:**
- Specific imports preferred: `from datetime import datetime` (not `import datetime`)
- Group-by-purpose imports: database-related imports grouped together

Example from `database.py`:
```python
import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
```

## Error Handling

**Patterns:**
- Context manager pattern for automatic cleanup: `with get_session() as session:`
- Try/except/finally pattern for manual cleanup with rollback on error:
```python
session = SessionLocal()
try:
    # work
    session.commit()
except Exception as e:
    session.rollback()
    raise
finally:
    session.close()
```
- Exception raised (not swallowed): `except Exception: ... raise`
- Database constraint violations produce SQLAlchemy exceptions (integrity errors, constraint errors)

**Current approach:**
- Validation on application layer (e.g., seat layout validation)
- Database constraints enforce data integrity (e.g., CHECK constraints, UNIQUE indexes)
- Foreign keys enforce referential integrity with CASCADE deletes where needed

## Logging

**Framework:** None detected in current code; `print()` used in test files

**Patterns:**
- Print statements for test output (e.g., `print("✓ Таблицы созданы")`)
- SQL query logging can be enabled via `SQL_ECHO` environment variable
- Logging to be implemented for production (not in MVP phase)

## Comments

**When to Comment:**
- Use docstrings (triple quotes) for modules, classes, and functions
- Inline comments for non-obvious logic or important constraints
- Comments in Russian (matching documentation language) or English
- Field comments via SQLAlchemy `comment=` parameter for database schema documentation

**JSDoc/TSDoc:**
- Python docstrings for all public modules, classes, methods
- Format: Triple-quoted strings at beginning of definition
- Include purpose, example usage where applicable

Example from `database.py`:
```python
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Automatically handles commit/rollback and session cleanup.

    Example:
        with get_session() as session:
            user = session.query(AppUser).filter_by(id=1).first()
            session.commit()
    """
```

## Function Design

**Size:** Functions are concise (average 5-20 lines)
- Context managers: minimal overhead, delegate to underlying session
- Query builders: direct SQLAlchemy queries
- Initialization functions: sequential setup steps

**Parameters:**
- Named parameters with type hints
- Foreign key IDs passed as parameters (e.g., `seller_id`, `buyer_vk_user_id`)
- Optional parameters marked with `Optional[T]`

**Return Values:**
- Context managers: yield session objects
- Query operations: return ORM model instances or lists
- Initialization: return None or yielded values

## Module Design

**Exports:**
- Model modules export single class (e.g., `models/user.py` exports `AppUser`)
- `models/__init__.py` aggregates and re-exports all models via `__all__` list

Example `models/__init__.py`:
```python
from models.base import Base
from models.user import AppUser
from models.vk_user import VkUser
# ... more imports

__all__ = [
    "Base",
    "AppUser",
    "VkUser",
    # ... more exports
]
```

**Barrel Files:**
- `models/__init__.py` acts as barrel file for model imports
- Centralizes model imports; single source for model definitions
- Enables: `from models import AppUser, Reservation` (not `from models.user import AppUser`)

**Database Module:**
- `database.py` exports: `engine`, `SessionLocal`, `get_session()`, `init_db()`
- Centralizes database connection logic
- Enables context manager pattern for session management

## SQLAlchemy Patterns

**ORM Model Declaration:**
- Use `Mapped[T]` type hints for all attributes
- Use `mapped_column()` for column definitions with constraints
- Use `ForeignKey()` with explicit table names and cascading rules
- Use `Index()` in `__table_args__` for indexes including partial indexes for SQLite

Example from `models/user.py`:
```python
class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[UserRole] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("app_users_role_idx", "role"),
        # ...
    )

    def __repr__(self) -> str:
        return f"AppUser(id={self.id!r}, role={self.role!r}, display_name={self.display_name!r})"
```

**Partial Indexes (SQLite):**
- Use `sqlite_where=text("condition")` in Index definitions
- Example: `Index(..., unique=True, sqlite_where=text("released_at IS NULL"))`
- Ensures uniqueness only for active records (not deleted/released records)

**Session Management:**
- Prefer context manager: `with get_session() as session:`
- Sessions handle commit/rollback automatically
- Flush before accessing generated IDs: `session.flush()`

**ENUM Types:**
- Inherit from `str` and `enum.Enum` for database string values
- Store lowercase string values: `ACTIVE = "active"` (not uppercase)
- Define in `models/base.py` for shared use

---

*Convention analysis: 2026-01-24*

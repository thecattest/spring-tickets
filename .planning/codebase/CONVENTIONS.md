# Coding Conventions

**Analysis Date:** 2026-02-19

## Naming Patterns

**Files:**
- Python modules: lowercase with underscores (e.g., `seat_parser.py`, `test_db_integration.py`)
- Test files: `test_*.py` prefix for pytest discovery
- Package directories: lowercase (e.g., `models/`, `bot/`, `handlers/`)
- Database initialization: `database.py`

**Functions:**
- Async handlers: descriptive with `_handler` or `_flow` suffix (e.g., `start_handler()`, `forwarded_message_handler()`, `start_payment_flow()`)
- Regular functions: lowercase with underscores (e.g., `parse_seats()`, `get_or_create_vk_user()`, `is_seat_available()`)
- Functions that check conditions: `is_*()` or `has_*()` prefix (e.g., `is_seat_available()`, `forwarded_has_receipt_attachment()`)
- Functions that retrieve data: `get_*()` prefix (e.g., `get_or_create_vk_user()`, `get_active_reservation()`, `get_layout()`)
- Database operations: prefixed with action (e.g., `create_reservation()`, `add_seats_to_reservation()`, `release_seats()`)
- Module initialization: `init_db()`, `setup_logging()`, `validate_config()`

**Variables:**
- Snake case throughout (e.g., `buyer_vk_id`, `reservation_id`, `display_name`, `state_peer`)
- Private/internal: no leading underscore convention observed
- Constants: UPPER_SNAKE_CASE (e.g., `SEAT_PRICE`, `REDIS_HOST`, `VK_BOT_TOKEN`, `COOKIE_MAX_AGE`)
- FSM states and enums: accessed as `BotState.MAIN_MENU`, `UserRole.ADMIN`
- Datetime fields: `created_at`, `last_activity_at`, `cancelled_at`, `released_at`
- User ID fields: `vk_user_id`, `buyer_vk_user_id`, `sold_by_user_id`, `created_by_user_id`

**Types/Classes:**
- Classes: PascalCase (e.g., `AppUser`, `Reservation`, `SeatAssignment`, `SeatParseError`, `DatabaseError`)
- Enum classes: PascalCase inheriting from `str, enum.Enum` (e.g., `UserRole`, `ReservationState`, `SeatStatus`, `ActorType`)
- Custom exceptions: PascalCase with `Error` suffix (e.g., `SeatOccupiedError`, `InsufficientSeatsError`, `PermissionError`, `SeatParseError`, `DatabaseError`)

## Code Style

**Formatting:**
- No explicit linting tool configured (no `.eslintrc`, `.flake8`, `pyproject.toml` detected)
- Manual style adherence observed
- Line length: no strict limit enforced
- Indentation: 4 spaces (Python standard)
- Type hints used consistently throughout

**Linting:**
- pytest used for testing
- No automatic formatting tools (like Black, isort) in use
- Code follows general PEP 8 conventions without strict enforcement

## Import Organization

**Order:**
1. Standard library (datetime, logging, os, pathlib, asyncio, etc.)
2. Third-party packages (sqlalchemy, vkbottle, fastapi, pytest, etc.)
3. Local imports (database, models, bot.*, etc.)

**Examples from codebase:**

From `bot/handlers/commands.py`:
```python
import logging
from vkbottle.bot import Bot, Message

from bot.fsm.states import BotState
from bot.fsm.storage import RedisStorage
from bot.keyboards import commands_keyboard
```

From `bot/utils/db.py`:
```python
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from models.vk_user import VkUser
from models.user import AppUser
from bot.config import SEAT_PRICE
```

**Path Aliases:**
- No path aliases configured; all imports use absolute paths from project root
- Imports from models use `from models import ClassName` (barrel file pattern)
- Imports from utils use `from bot.utils import db` or `from bot.utils.seat_parser import parse_seats`

**Barrel Files:**
- Used in `models/__init__.py` to export all model classes for simplified imports
- Used in `bot/__init__.py` with version export

## Error Handling

**Patterns:**

Custom exception classes for domain-specific errors:

From `bot/utils/db.py`:
```python
class DatabaseError(Exception):
    """Base exception for database operations."""
    pass

class SeatOccupiedError(DatabaseError):
    """Exception raised when trying to assign occupied seats."""
    def __init__(self, conflicts: list):
        self.conflicts = conflicts
        seats_str = ", ".join(f"{c['row']}/{c['seat']}" for c in conflicts)
        super().__init__(f"Seats already occupied: {seats_str}")

class InsufficientSeatsError(DatabaseError):
    """Exception raised when requested payment count exceeds available BOOKED seats."""
    def __init__(self, requested: int, available: int):
        self.requested = requested
        self.available = available
        super().__init__(f"Requested {requested} seats but only {available} BOOKED seats available")
```

Try/except with logging on failures:

From `bot/handlers/commands.py`:
```python
try:
    await storage.delete(message.from_id)
except Exception as e:
    logger.error(f"Error in /cancel: {e}")
    await message.answer("Операция отменена.")
```

From `bot/main.py` setup:
```python
try:
    config.validate_config()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    return None
```

Exception re-raising for validation:

From `bot/config.py`:
```python
def validate_config():
    """Validate required configuration is present."""
    errors = []
    if not VK_BOT_TOKEN:
        errors.append("VK_BOT_TOKEN is required")
    # ...
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
```

## Logging

**Framework:** Python's built-in `logging` module

**Patterns:**
- Logger created per module: `logger = logging.getLogger(__name__)`
- Configured centrally in `bot/config.py` via `setup_logging()`
- Log levels used: INFO for major events, ERROR for failures, DEBUG for detailed traces
- Third-party loggers (vkbottle, aiohttp) suppressed at WARNING level

From `bot/config.py`:
```python
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Suppress noisy third-party loggers
logging.getLogger("vkbottle").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
```

From `bot/handlers/commands.py`:
```python
logger.info(f"User {message.from_id} sent /start")
logger.error(f"Error in /cancel: {e}")
```

From `bot/utils/seat_parser.py`:
```python
logger.debug(f"Parsed seats: {text} -> {seats}")
```

## Comments

**When to Comment:**
- Module docstrings: always present, describe purpose and usage
- Function docstrings: present for public functions and handlers
- Inline comments: minimal; code is self-documenting
- Intent comments: used sparingly to explain "why" not "what"

From `models/base.py`:
```python
"""
Base declarative class and ENUM types for SQLAlchemy ORM models.
"""
```

From `bot/utils/seat_parser.py` module docstring:
```python
"""
Seat input parser.

Supports multiple input formats:
- Spaces: "5 6 7" -> [5, 6, 7]
- Commas: "5, 6, 7" -> [5, 6, 7]
- Ranges: "5-7" -> [5, 6, 7]
- Mixed: "1, 3, 5-7" -> [1, 3, 5, 6, 7]
"""
```

**Docstrings:**
- Google-style for parameters and return values
- Present on functions with complex logic or public APIs
- Include Raises section for functions that throw exceptions

From `bot/utils/db.py`:
```python
def get_or_create_vk_user(vk_id: int, display_name: str) -> VkUser:
    """
    Get existing VK user or create new one.

    Args:
        vk_id: VK user ID
        display_name: Display name from VK

    Returns:
        VkUser instance

    Raises:
        DatabaseError: If operation fails
    """
```

## Function Design

**Size:**
- Functions typically 20-80 lines
- Handler functions often 40-60 lines with multiple logical branches
- Database utility functions kept focused (20-40 lines)
- Parse/format utility functions compact (30-50 lines)
- Async handlers: accept Message and storage parameters

**Parameters:**
- Functions rarely exceed 4-5 parameters
- Type hints used consistently
- Handlers follow pattern: `async def handler(message: Message, storage: RedisStorage):`

From `bot/handlers/reservation.py`:
```python
async def forwarded_message_handler(message: Message, storage: RedisStorage):
    """Handle forwarded message - create or show existing reservation."""
```

From `web/app.py`:
```python
def hall(request: Request):
def is_authenticated(request: Request) -> bool:
```

**Return Values:**
- Functions return meaningful values or None on error
- Exception raising preferred to returning None for critical operations
- Custom exception types used for specific error conditions
- Async handlers may not return values (communicate via message.answer())

## Module Design

**Exports:**
- Barrel files list exports in `__all__` (e.g., `models/__init__.py`)
- Public functions and classes use docstrings to indicate API

From `models/__init__.py`:
```python
__all__ = [
    "Base",
    "AppUser",
    "VkUser",
    "Reservation",
    "SeatAssignment",
    "Payment",
    "PaymentSeat",
    "ReconcileCheckpoint",
    "AuditLog",
]
```

**Barrel Files:**
- Used to simplify imports from packages
- Example: `from models import AppUser, Reservation` instead of `from models.user import AppUser`
- Encourages encapsulation and reduces import path complexity

---

*Convention analysis: 2026-02-19*

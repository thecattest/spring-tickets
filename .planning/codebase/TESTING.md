# Testing Patterns

**Analysis Date:** 2026-01-24

## Test Framework

**Runner:**
- Not formally configured yet (MVP phase)
- Planned: pytest (common Python standard) or unittest
- Current: Manual test script approach

**Current Test File:**
- `test_db.py` at project root - manual integration test

**Assertion Library:**
- Python built-in `assert` statements (implicit)
- Planned: pytest or unittest assertions

**Run Commands:**
```bash
python test_db.py                # Run database integration test (current)
# Planned:
pytest tests/                     # Run all tests (when pytest is added)
pytest tests/ -v                  # Verbose output
pytest tests/ --cov=src          # With coverage report
```

## Test File Organization

**Current Location:**
- `test_db.py` at project root (alongside source code)

**Planned Structure:**
- Dedicated `tests/` directory at project root
- Test files mirror source structure: `tests/models/test_user.py` for `models/user.py`
- Integration tests in `tests/integration/`

**Naming:**
- Current: `test_db.py` (integration test)
- Planned: `test_*.py` or `*_test.py` per file (pytest convention: `test_*.py`)

**Structure:**
```
tests/
├── conftest.py                 # Shared fixtures and configuration
├── unit/
│   ├── models/
│   │   ├── test_user.py
│   │   ├── test_reservation.py
│   │   └── test_seat_assignment.py
│   └── test_database.py
├── integration/
│   ├── test_reservation_workflow.py
│   ├── test_payment_workflow.py
│   └── test_financial_reconciliation.py
└── fixtures/
    ├── users.py               # Test user factories
    ├── reservations.py        # Test reservation factories
    └── seat_data.py           # Test seat data
```

## Test Structure

**Current Pattern (from `test_db.py`):**

```python
def test_database():
    """Тест создания БД и базовых операций."""

    print("=" * 60)
    print("Тестирование SQLite базы данных")
    print("=" * 60)

    # 1. Инициализация БД
    print("\n1. Инициализация БД...")
    init_db()
    print("✓ Таблицы созданы")

    # 2. Создание тестовых данных
    print("\n2. Создание тестовых данных...")
    with get_session() as session:
        # Create test data
        pass

    # 3. Проверка данных
    print("\n3. Проверка созданных данных...")
    with get_session() as session:
        # Query and verify
        pass

    # 4. Проверка ограничений
    print("\n4. Проверка уникальности активных мест...")
    try:
        with get_session() as session:
            # Try to violate constraint
            session.add(duplicate_seat)
            session.commit()
        print("✗ ОШИБКА: дубликат не был заблокирован!")
    except Exception as e:
        print(f"✓ Дубликат заблокирован (ожидаемо): {type(e).__name__}")

if __name__ == "__main__":
    test_database()
```

**Planned Pytest Pattern:**

```python
import pytest
from datetime import datetime
from database import get_session
from models import AppUser, VkUser, Reservation, SeatAssignment
from models.base import UserRole, ReservationState, SeatStatus

class TestReservationCreation:
    """Tests for reservation creation workflow."""

    @pytest.fixture
    def seller(self):
        """Create test seller user."""
        with get_session() as session:
            seller = AppUser(
                role=UserRole.SELLER,
                display_name="Test Seller"
            )
            session.add(seller)
            return seller

    def test_create_reservation_with_seats(self, seller):
        """Test creating a reservation with multiple seats."""
        with get_session() as session:
            # Setup
            buyer = VkUser(vk_user_id=123456, display_name="Buyer")
            session.add(buyer)
            session.flush()

            # Action
            reservation = Reservation(
                buyer_vk_user_id=buyer.id,
                sold_by_user_id=seller.id
            )
            session.add(reservation)
            session.flush()

            # Assert
            assert reservation.id is not None
            assert reservation.state == ReservationState.ACTIVE
```

**Patterns Observed:**
- Setup/Action/Assert pattern implicit in test code
- No teardown needed (tests use fresh database or per-test fixtures)
- Integration tests work with actual SQLAlchemy ORM
- Context manager ensures session cleanup

## Mocking

**Framework:** Not yet implemented

**Current Approach:**
- No mocking in current tests - direct database interaction
- Tests use real SQLite database (`tickets.db`)

**Planned Strategy:**
- Mock external APIs (VK integration, payment webhooks)
- Mock datetime for testing time-based logic (7-day debtors)
- Real database sessions for ORM tests (no mocking database layer)

**Planned Mocking Pattern:**
```python
from unittest.mock import patch, MagicMock

def test_vk_webhook_handling():
    """Test incoming VK payment webhook."""
    with patch('vk_client.send_message') as mock_send:
        # Test code
        pass

def test_reminder_for_debtors(freezegun_datetime):
    """Test 7-day reminder for unpaid reservations."""
    # freezegun to control datetime
    freezegun_datetime.move_to("2026-02-01")
    # Test code expects different reservations based on date
```

**What to Mock:**
- External API calls (VK API, payment services)
- Datetime for time-sensitive logic
- File system access (if reading layout.json)

**What NOT to Mock:**
- Database layer (test with real SQLite)
- ORM models (use actual model classes)
- Session management (use `get_session()` context manager)
- Core business logic (test directly)

## Fixtures and Factories

**Test Data Pattern (from `test_db.py`):**

```python
def test_database():
    # ... setup ...
    with get_session() as session:
        # Create admin
        admin = AppUser(
            role=UserRole.ADMIN,
            display_name="Администратор",
            is_active=True
        )
        session.add(admin)

        # Create seller
        seller = AppUser(
            role=UserRole.SELLER,
            display_name="Иван Иванов",
            vk_user_id=123456
        )
        session.add(seller)
        session.flush()  # Get IDs before using in FK

        # Create buyer
        buyer = VkUser(
            vk_user_id=987654321,
            display_name="Петр Петров"
        )
        session.add(buyer)
        session.flush()
```

**Planned Factory Pattern:**

```python
# tests/fixtures/users.py
from models import AppUser, VkUser
from models.base import UserRole

class UserFactory:
    """Factory for creating test users."""

    @staticmethod
    def create_seller(session, **kwargs):
        """Create test seller user."""
        defaults = {
            "role": UserRole.SELLER,
            "display_name": "Test Seller",
            "is_active": True
        }
        defaults.update(kwargs)
        user = AppUser(**defaults)
        session.add(user)
        session.flush()
        return user

    @staticmethod
    def create_vk_user(session, **kwargs):
        """Create test VK user."""
        defaults = {
            "vk_user_id": 987654321,
            "display_name": "Test Buyer"
        }
        defaults.update(kwargs)
        user = VkUser(**defaults)
        session.add(user)
        session.flush()
        return user

# tests/conftest.py
@pytest.fixture
def seller(session):
    """Provide a test seller."""
    return UserFactory.create_seller(session)

@pytest.fixture
def buyer(session):
    """Provide a test VK buyer."""
    return UserFactory.create_vk_user(session)
```

**Location:**
- `tests/conftest.py` for shared fixtures (pytest convention)
- `tests/fixtures/` directory for factory classes
- Factories create test data with sensible defaults, allow overrides

## Coverage

**Requirements:** Not enforced in MVP phase

**Planned Coverage Targets:**
- Unit tests: Core business logic (>80%)
- Integration tests: Database operations (>70%)
- E2E tests: Critical workflows (reservation, payment, reconciliation)

**View Coverage (Planned):**
```bash
pytest --cov=src --cov=models --cov-report=html
# Open htmlcov/index.html in browser
```

## Test Types

**Unit Tests:**
- Scope: Individual functions, business logic
- Location: `tests/unit/`
- Approach: Fast, isolated, mock external dependencies
- Example: Testing validation logic for seat coordinates, date calculations for reminders

**Integration Tests:**
- Scope: Multi-model workflows, database operations
- Location: `tests/integration/`
- Approach: Use real database (test SQLite), no mocking ORM layer
- Example: Full reservation flow (create reservation → add seats → record payment → update statuses)

**E2E Tests:**
- Status: Not planned for MVP
- Planned: HTTP endpoints + database (when API layer added)
- Framework: Would use pytest + httpx or requests

## Common Patterns

**Async Testing:**
- Not applicable: Current codebase is synchronous
- Planned: If async SQLAlchemy added later, use `pytest-asyncio`

**Error Testing (from `test_db.py`):**

```python
# Test that constraint violations raise exceptions
try:
    with get_session() as session:
        # Try to violate unique constraint
        duplicate_seat = SeatAssignment(
            row_number=10,
            seat_number=5,  # Already booked
            status=SeatStatus.BOOKED,
            created_by_user_id=1
        )
        session.add(duplicate_seat)
        session.commit()
    print("✗ ОШИБКА: дубликат не был заблокирован!")
except Exception as e:
    print(f"✓ Дубликат заблокирован (ожидаемо): {type(e).__name__}")
```

**Planned Error Testing Pattern:**

```python
def test_duplicate_seat_assignment_blocked():
    """Test that duplicate active seat assignments are blocked."""
    with get_session() as session:
        # Create first seat assignment
        seat1 = SeatAssignment(
            row_number=5,
            seat_number=10,
            status=SeatStatus.BOOKED,
            created_by_user_id=1
        )
        session.add(seat1)
        session.commit()

        # Try to create duplicate
        with pytest.raises(IntegrityError):
            seat2 = SeatAssignment(
                row_number=5,
                seat_number=10,
                status=SeatStatus.BOOKED,
                created_by_user_id=1
            )
            session.add(seat2)
            session.commit()

def test_released_seat_can_be_reassigned():
    """Test that a released seat can be assigned to new reservation."""
    with get_session() as session:
        # Create and release first assignment
        seat1 = SeatAssignment(
            row_number=5,
            seat_number=10,
            status=SeatStatus.BOOKED,
            created_by_user_id=1
        )
        session.add(seat1)
        session.flush()
        seat1.released_at = datetime.utcnow()

        # Should allow new assignment to same seat
        seat2 = SeatAssignment(
            row_number=5,
            seat_number=10,
            status=SeatStatus.BOOKED,
            created_by_user_id=1,
            reservation_id=2
        )
        session.add(seat2)
        session.commit()  # Should not raise

        assert seat2.id is not None
```

**Database Fixture Pattern:**

```python
@pytest.fixture
def db_session(tmp_path):
    """Provide clean database session for each test."""
    # Create test database
    test_db_path = str(tmp_path / "test.db")
    test_engine = create_engine(f"sqlite:///{test_db_path}")

    # Initialize schema
    Base.metadata.create_all(bind=test_engine)

    # Create session
    TestSessionLocal = sessionmaker(bind=test_engine)
    session = TestSessionLocal()

    yield session

    # Cleanup
    session.close()
    test_engine.dispose()
```

---

*Testing analysis: 2026-01-24*

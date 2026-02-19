# Testing Patterns

**Analysis Date:** 2026-02-19

## Test Framework

**Runner:**
- pytest 7.0.0+
- Config: No `pytest.ini` or explicit pytest configuration; uses pytest defaults from `requirements.txt`

**Assertion Library:**
- pytest built-in assertions
- Custom assertions via `pytest.raises()` for exception testing

**Run Commands:**
```bash
pytest                                    # Run all tests
pytest -v                                 # Verbose output
pytest bot/tests/                         # Run specific directory
pytest bot/tests/test_db_integration.py   # Run specific test file
pytest -k "test_seat"                     # Run tests matching pattern
pytest --tb=short                         # Short traceback format
pytest --cov=bot --cov=models             # With coverage report
```

## Test File Organization

**Location:**
- Co-located within modules under `tests/` subdirectory
- Main database test at root: `test_db.py` (integration test script)
- Bot tests in: `bot/tests/test_*.py`

**Naming:**
- Test files: `test_*.py` prefix (pytest convention)
- Test classes: `Test*` PascalCase (e.g., `TestVkUserOperations`, `TestSeatOperations`)
- Test methods: `test_*` lowercase with underscores (e.g., `test_create_vk_user()`, `test_seat_occupied()`)

**Directory Structure:**
```
project-root/
├── test_db.py                      # Root-level database initialization test
├── bot/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_db_integration.py  # Integration tests for database operations
│   │   ├── test_redis_fsm.py       # FSM state management tests
│   │   └── test_seat_parser.py     # Seat parsing utility tests
```

## Test Structure

**Suite Organization:**

Pytest class-based organization with fixtures from `bot/tests/test_db_integration.py`:

```python
@pytest.fixture(scope="function")
def test_db():
    """
    Create a temporary test database.

    Yields:
        Database engine
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    test_db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = test_db_url

    from database import engine
    Base.metadata.create_all(bind=engine)

    yield engine

    os.unlink(db_path)


@pytest.fixture(scope="function")
def test_seller(test_db):
    """Create a test seller user."""
    with SessionLocal() as session:
        seller = AppUser(
            role=UserRole.SELLER,
            display_name="Test Seller",
            is_active=True,
        )
        session.add(seller)
        session.commit()
        session.refresh(seller)
        return seller


class TestVkUserOperations:
    """Test VK user database operations."""

    def test_create_vk_user(self, test_db):
        """Test creating new VK user."""
        vk_user = db.get_or_create_vk_user(12345, "Test User")

        assert vk_user.id is not None
        assert vk_user.vk_user_id == 12345
        assert vk_user.display_name == "Test User"
```

**Patterns:**
- Setup: Use pytest fixtures with `scope="function"` for test isolation
- Teardown: Cleanup in fixture yield block or context managers
- Test naming: `test_<action>_<expected_outcome>` (e.g., `test_add_seats_conflict()`)
- Assertion: Simple assert statements with meaningful values
- Grouping: Test classes group related functionality

## Mocking

**Framework:**
- No explicit mocking library (no unittest.mock or pytest-mock detected)
- Database isolation via temporary SQLite files (preferred over mocking)
- Manual fixture creation for test data

**Patterns:**

Exception testing from `bot/tests/test_seat_parser.py`:
```python
def test_empty_input(self):
    """Test empty input raises error."""
    with pytest.raises(SeatParseError, match="не может быть пустым"):
        parse_seats("")
```

From `bot/tests/test_db_integration.py`:
```python
def test_add_seats_conflict(self, test_db, test_seller):
    """Test adding seats with conflict."""
    vk_user1 = db.get_or_create_vk_user(12345, "User 1")
    reservation1 = db.create_reservation(vk_user1.id, test_seller.id)
    db.add_seats_to_reservation(reservation1.id, 1, [5], test_seller.id)

    vk_user2 = db.get_or_create_vk_user(67890, "User 2")
    reservation2 = db.create_reservation(vk_user2.id, test_seller.id)

    with pytest.raises(db.SeatOccupiedError) as exc_info:
        db.add_seats_to_reservation(reservation2.id, 1, [5], test_seller.id)

    assert len(exc_info.value.conflicts) == 1
    assert exc_info.value.conflicts[0]['row'] == 1
    assert exc_info.value.conflicts[0]['seat'] == 5
```

**What to Mock:**
- External API calls (VK API) - currently not mocked but isolated in handlers
- Time-dependent operations - fixtures use real datetime

**What NOT to Mock:**
- Database operations - use real temporary SQLite for testing
- Business logic functions - test actual behavior
- String parsing/formatting - test actual output
- ORM models - test with actual model classes

## Fixtures and Factories

**Test Data:**

From `bot/tests/test_db_integration.py`:
```python
@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    test_db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = test_db_url

    from database import engine
    Base.metadata.create_all(bind=engine)

    yield engine

    os.unlink(db_path)

@pytest.fixture(scope="function")
def test_seller(test_db):
    """Create a test seller user fixture."""
    with SessionLocal() as session:
        seller = AppUser(
            role=UserRole.SELLER,
            display_name="Test Seller",
            is_active=True,
        )
        session.add(seller)
        session.commit()
        session.refresh(seller)
        return seller
```

**Location:**
- Fixtures defined in test files themselves (no shared `conftest.py`)
- Each test file is self-contained
- Database fixture at function scope ensures isolation between tests

**Fixture Dependencies:**
Fixtures can depend on other fixtures for composition:
```python
def test_seller(test_db):  # Depends on test_db fixture
    # Creates session using SessionLocal which uses injected DATABASE_URL
```

## Coverage

**Requirements:**
- No coverage requirements enforced
- No `.coveragerc` or coverage configuration file present

**View Coverage:**
```bash
pytest --cov=bot --cov=models --cov-report=html
# View report in htmlcov/index.html
```

## Test Types

**Unit Tests:**
- Individual function testing in isolation
- Examples: `test_space_separated()`, `test_invalid_characters()`, `test_empty_input()`
- Location: `bot/tests/test_seat_parser.py`
- Focus: Parser logic, validation, error cases

**Integration Tests:**
- Database operation testing with real schema
- Examples: `test_create_reservation()`, `test_add_seats_to_reservation()`, `test_seat_occupied()`
- Location: `bot/tests/test_db_integration.py`
- Uses: Temporary SQLite databases created per test for isolation

**E2E Tests:**
- Not present in current codebase
- VK bot handlers not tested end-to-end (async handler testing would require different setup)

## Common Patterns

**Async Testing:**
No async tests currently; VK handlers use async but are not tested.

**Error Testing:**

From `bot/tests/test_seat_parser.py`:
```python
def test_empty_input(self):
    """Test empty input raises error."""
    with pytest.raises(SeatParseError, match="не может быть пустым"):
        parse_seats("")

def test_reversed_range(self):
    """Test reversed range raises error."""
    with pytest.raises(SeatParseError, match="больше конца"):
        parse_seats("7-5")

def test_invalid_characters(self):
    """Test invalid characters raise error."""
    with pytest.raises(SeatParseError, match="Неверный формат"):
        parse_seats("abc")
```

From `bot/tests/test_db_integration.py`:
```python
def test_add_seats_atomic(self, test_db, test_seller):
    """Test that seat addition is atomic."""
    # Create and add partial seats
    vk_user1 = db.get_or_create_vk_user(12345, "User 1")
    reservation1 = db.create_reservation(vk_user1.id, test_seller.id)

    # Create second reservation
    vk_user2 = db.get_or_create_vk_user(67890, "User 2")
    reservation2 = db.create_reservation(vk_user2.id, test_seller.id)

    # Try to add conflicting seats (should fail atomically)
    with pytest.raises(db.SeatOccupiedError):
        db.add_seats_to_reservation(reservation2.id, 1, [5, 6, 7], test_seller.id)
```

**Database Isolation:**
- Each function-scoped fixture creates temporary SQLite file
- Automatic cleanup via os.unlink() in fixture teardown
- Prevents test pollution and race conditions

**Class-based Test Organization:**
Tests grouped by operation type:
- `TestVkUserOperations` - user creation and retrieval
- `TestReservationOperations` - reservation management
- `TestSeatOperations` - seat availability and assignment

**Test Method Naming Convention:**

Pattern: `test_<subject>_<condition>` or `test_<subject>_<scenario>`

Examples:
- `test_create_vk_user()` - action
- `test_get_existing_vk_user()` - retrieval
- `test_seat_occupied()` - state check
- `test_add_seats_conflict()` - error condition
- `test_add_seats_atomic()` - transaction behavior

---

*Testing analysis: 2026-02-19*

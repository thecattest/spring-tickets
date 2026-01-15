# SQLAlchemy Models — Инструкция по использованию

Этот проект использует SQLAlchemy 2.0+ ORM для работы с SQLite3 базой данных (для MVP).

## Установка зависимостей

```bash
pip install -r requirements.txt
```

SQLite3 встроен в Python, дополнительные драйверы не нужны.

## Настройка подключения к БД

По умолчанию используется SQLite файл `tickets.db` в корне проекта.

Для использования другой БД укажите DATABASE_URL через переменную окружения:

```bash
# SQLite (по умолчанию)
export DATABASE_URL="sqlite:///tickets.db"

# PostgreSQL (если понадобится позже, нужно установить psycopg2-binary)
export DATABASE_URL="postgresql+psycopg2://user:password@host:port/dbname"
```

## Инициализация БД (создание таблиц)

```python
from database import init_db

init_db()
```

Или из командной строки:

```bash
python database.py
```

## Использование сессий

### Вариант 1: Context manager (рекомендуется)

```python
from database import get_session
from models import AppUser, Reservation, SeatAssignment

with get_session() as session:
    # Чтение
    user = session.query(AppUser).filter_by(id=1).first()
    
    # Создание
    new_user = AppUser(
        role=UserRole.SELLER,
        display_name="Иван Иванов"
    )
    session.add(new_user)
    
    # Обновление
    user.display_name = "Новое имя"
    
    # Удаление
    session.delete(user)
    
    # Коммит произойдет автоматически при выходе из блока with
```

### Вариант 2: Ручное управление

```python
from database import SessionLocal
from models import VkUser

session = SessionLocal()
try:
    vk_user = VkUser(
        vk_user_id=123456789,
        display_name="Петр Петров",
        profile_url="https://vk.com/id123456789"
    )
    session.add(vk_user)
    session.commit()
except Exception as e:
    session.rollback()
    raise
finally:
    session.close()
```

## Структура моделей

### Базовый класс и ENUM'ы

- `models/base.py`: `Base` (DeclarativeBase) и все ENUM типы
  - `UserRole` (admin, seller)
  - `ReservationState` (active, cancelled)
  - `SeatStatus` (booked, paid, reserved)
  - `ActorType` (user, system)

### Модели

- `models/user.py`: `AppUser` — пользователи системы (админ/билетер)
- `models/vk_user.py`: `VkUser` — покупатели (VK-аккаунты)
- `models/reservation.py`: `Reservation` — брони
- `models/seat_assignment.py`: `SeatAssignment` — единая таблица занятости мест
- `models/payment.py`: `Payment`, `PaymentSeat` — оплаты и привязка к местам
- `models/expense.py`: `Expense` — расходы
- `models/reconcile.py`: `ReconcileCheckpoint` — чекапы финансов
- `models/audit.py`: `AuditLog` — аудит-лог

## Примеры запросов

### Создать бронь и добавить места

```python
from database import get_session
from models import Reservation, SeatAssignment, VkUser, AppUser
from models.base import ReservationState, SeatStatus

with get_session() as session:
    # Найти покупателя и продавца
    buyer = session.query(VkUser).filter_by(vk_user_id=123456).first()
    seller = session.query(AppUser).filter_by(id=1).first()
    
    # Создать бронь
    reservation = Reservation(
        buyer_vk_user_id=buyer.id,
        sold_by_user_id=seller.id,
        state=ReservationState.ACTIVE
    )
    session.add(reservation)
    session.flush()  # Получить ID брони
    
    # Добавить места
    for seat_num in [1, 2, 3]:
        seat = SeatAssignment(
            row_number=5,
            seat_number=seat_num,
            status=SeatStatus.BOOKED,
            reservation_id=reservation.id,
            created_by_user_id=seller.id
        )
        session.add(seat)
```

### Найти "должников" (неоплаченные брони старше 7 дней)

```python
from datetime import datetime, timedelta
from database import get_session
from models import Reservation, SeatAssignment
from models.base import ReservationState, SeatStatus

with get_session() as session:
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    debtors = (
        session.query(Reservation)
        .filter(
            Reservation.state == ReservationState.ACTIVE,
            Reservation.sold_by_user_id == seller_id,
            Reservation.last_activity_at <= week_ago
        )
        .join(SeatAssignment)
        .filter(
            SeatAssignment.released_at.is_(None),
            SeatAssignment.status == SeatStatus.BOOKED
        )
        .all()
    )
```

### Получить статус места

```python
from database import get_session
from models import SeatAssignment

with get_session() as session:
    seat = (
        session.query(SeatAssignment)
        .filter(
            SeatAssignment.row_number == 5,
            SeatAssignment.seat_number == 12,
            SeatAssignment.released_at.is_(None)
        )
        .first()
    )
    
    if seat is None:
        print("Место свободно")
    else:
        print(f"Место занято: {seat.status}")
```

## Важные замечания

1. **SQLite для MVP**: используется SQLite3 для быстрого прототипирования. Модели готовы для миграции на PostgreSQL при необходимости.
2. **Foreign Keys в SQLite**: автоматически включены в `database.py` для корректной работы CASCADE deletes.
3. **Partial indexes**: уникальность активных мест гарантируется частичным индексом `WHERE released_at IS NULL` (SQLite поддерживает с версии 3.8.0+).
4. **Валидация мест**: проверка существования ряда/места по `layout.json` выполняется на уровне приложения.
5. **last_activity_at**: обновляется при любом действии с бронью (добавление/снятие мест, оплата).
6. **Cascades**: при удалении брони автоматически удаляются связанные места (`ON DELETE CASCADE`).

## Дополнительные файлы

- `TZ.md` — техническое задание с требованиями
- `DB_SCHEMA.md` — подробная схема БД с SQL DDL и примерами запросов

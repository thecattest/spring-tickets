# Phase 1: Основа бота и создание броней

**Status:** 🔜 PENDING
**Goal:** Минимальный рабочий бот для создания броней и добавления мест
**Effort:** 15-20 hours

---

## Tasks

### 1. Project Setup

- [ ] Создать структуру проекта bot/ (согласно BOT_SPEC.md structure)
- [ ] Создать requirements.txt с зависимостями (vkbottle, redis, SQLAlchemy, python-dotenv)
- [ ] Создать .env.example с шаблоном конфигурации
- [ ] Инициализировать VKBottle с токеном из .env
- [ ] Настроить подключение к Redis для FSM storage
- [ ] Настроить подключение к SQLite БД

**Files to create:**
- `bot/__init__.py`
- `bot/main.py`
- `bot/config.py`
- `requirements.txt`
- `.env.example`

---

### 2. FSM Configuration

- [ ] Настроить Redis FSM storage (permanent, no TTL)
- [ ] Определить FSM states в bot/fsm/states.py:
  - IDLE
  - AWAITING_ROW
  - AWAITING_SEATS
  - SEAT_ADDITION_MENU
- [ ] Создать FSM storage wrapper в bot/fsm/storage.py
- [ ] Настроить key pattern: `bot:fsm:{vk_user_id}`

**Files to create:**
- `bot/fsm/__init__.py`
- `bot/fsm/states.py`
- `bot/fsm/storage.py`

---

### 3. Layout Loading

- [ ] Создать bot/utils/layout.py для загрузки layout.json
- [ ] Парсить layout.json при старте бота
- [ ] Кешировать в памяти структуру зала
- [ ] Функция get_seat_count(row: int) -> int для валидации
- [ ] Функция is_valid_seat(row: int, seat: int) -> bool

**Files to create:**
- `bot/utils/layout.py`

---

### 4. Seat Parser

- [ ] Создать bot/utils/seat_parser.py
- [ ] Парсить пробелы: "5 6 7" → [5, 6, 7]
- [ ] Парсить запятые: "5, 6, 7" → [5, 6, 7]
- [ ] Парсить диапазоны: "5-7" → [5, 6, 7]
- [ ] Парсить комбинации: "1, 3, 5-7" → [1, 3, 5, 6, 7]
- [ ] Валидация формата (только цифры, пробелы, запятые, тире)
- [ ] Обработка ошибок с понятными сообщениями

**Files to create:**
- `bot/utils/seat_parser.py`

**Test cases:**
```python
"5 6 7" → [5, 6, 7]
"5, 6, 7" → [5, 6, 7]
"5-7" → [5, 6, 7]
"1, 3, 5-7" → [1, 3, 5, 6, 7]
"1-3, 5, 7-9" → [1, 2, 3, 5, 7, 8, 9]
```

---

### 5. Database Integration

- [ ] Создать bot/utils/db.py с функциями:
  - `get_or_create_vk_user(vk_id, display_name) -> VkUser`
  - `get_active_reservation(vk_user_id) -> Optional[Reservation]`
  - `create_reservation(buyer_vk_user_id, sold_by_user_id) -> Reservation`
  - `is_seat_available(row, seat) -> bool`
  - `add_seats_to_reservation(reservation_id, row, seats, user_id) -> List[SeatAssignment]`
- [ ] Все операции в транзакциях (`with db.begin()`)
- [ ] Обработка IntegrityError для занятых мест
- [ ] Обновление Reservation.last_activity_at

**Files to create:**
- `bot/utils/db.py`

---

### 6. Basic Commands

- [ ] Обработчик /start:
  - Приветствие
  - Краткое описание команд
  - Инструкция "переслать сообщение клиента"
- [ ] Обработчик /help:
  - Полная справка по командам
  - Форматы ввода мест (пробел/запятая/диапазон)
  - Примеры
- [ ] Обработчик /cancel:
  - Сброс FSM state → IDLE
  - Очистка временных данных из Redis
  - Подтверждение отмены

**Files to create:**
- `bot/handlers/commands.py`

---

### 7. Reservation Creation Handler

- [ ] Обработчик пересылки сообщения (forwarded message):
  - Получить VK user ID автора пересланного сообщения
  - Проверить: есть ли активная бронь у этого клиента?
  - Если НЕТ: создать бронь → перейти в AWAITING_ROW
  - Если ДА: показать главное меню (оставить для Phase 2)
  - Сохранить контекст в Redis (reservation_id, buyer_vk_user_id)

**Files to update:**
- `bot/handlers/reservation.py` (new)

**FSM flow:**
```
IDLE → (forward message) → AWAITING_ROW
```

---

### 8. Seat Addition Flow

- [ ] State AWAITING_ROW:
  - Ожидание ввода номера ряда
  - Валидация: ряд 1-24
  - Ошибка: "Неверный ряд. Допустимые значения: 1-24"
  - Сохранить row в Redis context
  - Переход в AWAITING_SEATS

- [ ] State AWAITING_SEATS:
  - Ожидание ввода мест
  - Парсинг через seat_parser
  - Валидация: места 1-{seatCount для данного ряда}
  - Проверка занятости: is_seat_available для каждого
  - Если хотя бы одно занято → отклонить все (атомарность)
  - Ошибка занятости: показать какие места заняты + статус (Бронь/Резерв + комментарий)
  - Добавить места через add_seats_to_reservation
  - Отобразить подтверждение + общее количество мест в брони
  - Переход в SEAT_ADDITION_MENU

- [ ] State SEAT_ADDITION_MENU:
  - Кнопки: [Добавить еще] [Готово]
  - [Добавить еще] → возврат в AWAITING_ROW
  - [Готово] → генерация скрипта + переход в IDLE

**Files to update:**
- `bot/handlers/reservation.py`

**Error messages:**
- Row error: "Неверный ряд. Допустимые значения: 1-24. Введите ряд:"
- Seat format error: "Неверный формат. Введите номера мест через пробел, запятые или диапазон. Примеры: '5 6 7' или '5, 6, 7' или '5-7'"
- Seat range error: "Недопустимые номера мест. Для ряда {row} доступны места 1-{seatCount}."
- Occupied error: "Места уже заняты:\n• Ряд {row}, место {seat} — {status} ({detail})\nВведите другие места:"

---

### 9. Script Generation

- [ ] Создать bot/messages.py с шаблоном скрипта
- [ ] Генерация скрипта при нажатии [Готово]:
  - Имя клиента (VkUser.display_name)
  - Список мест (сгруппированных по рядам)
  - Общее количество мест
  - Сумма к оплате (если SEAT_PRICE задан в .env)
  - Место для пользовательского текста
- [ ] Отправка скрипта билетеру
- [ ] Очистка FSM state → IDLE

**Files to create:**
- `bot/messages.py`

**Template:**
```
Бронь сохранена.

Скрипт для отправки клиенту:

Добрый день, {Имя}! Ваша бронь:
{Ряд X, места Y, Z}
{Ряд W, места A, B, C}

[Место для вашего текста]

Всего: {N} мест
К оплате: {сумма} руб.

Спасибо за бронь!
```

---

### 10. Keyboards

- [ ] Создать bot/keyboards.py с генераторами клавиатур
- [ ] seat_addition_menu_keyboard() → [Добавить еще] [Готово]
- [ ] Использовать VK Keyboard API

**Files to create:**
- `bot/keyboards.py`

---

### 11. Error Handling

- [ ] Centralized error handler в bot/utils/errors.py
- [ ] Обработка IntegrityError (seat conflicts)
- [ ] Обработка RedisConnectionError
- [ ] Обработка DatabaseError
- [ ] Логирование всех ошибок
- [ ] User-friendly сообщения (не показывать stack traces)

**Files to create:**
- `bot/utils/errors.py`

---

### 12. Logging

- [ ] Настроить logging в bot/config.py
- [ ] Уровни: DEBUG, INFO, WARNING, ERROR
- [ ] Формат: timestamp, level, message
- [ ] Логирование всех FSM transitions
- [ ] Логирование всех DB operations
- [ ] Логирование всех errors

---

### 13. Testing

- [ ] Тест seat_parser (все форматы)
- [ ] Тест layout loading
- [ ] Тест database functions (с test DB)
- [ ] Integration test: create reservation flow
- [ ] Integration test: add seats with conflicts

**Files to create:**
- `bot/tests/__init__.py`
- `bot/tests/test_seat_parser.py`
- `bot/tests/test_db_integration.py`

---

## Success Criteria

- ✅ Билетер может переслать сообщение клиента и создать бронь
- ✅ Можно добавить места в любом формате (пробел/запятая/диапазон)
- ✅ Проверка занятости работает корректно
- ✅ Если хотя бы одно место занято — отклоняются все (атомарность)
- ✅ Ошибки ввода обрабатываются понятными сообщениями
- ✅ FSM состояние сохраняется в Redis permanent
- ✅ Скрипт генерируется и отправляется при [Готово]
- ✅ Бот стабильно работает без crashes

---

## Dependencies

**Requires:**
- Phase 0 completed ✅
- layout.json exists ✅
- models/* ready ✅
- Redis instance running
- VK Bot API token

**Provides:**
- Basic bot infrastructure
- Reservation creation
- Seat addition with validation
- Script generation

**Blocks:**
- Phase 2 (main menu and seat deletion)

---

## Technical Notes

- Redis keys: `bot:fsm:{vk_user_id}` → JSON state
- DB transactions: `with db.begin()` for atomicity
- Audit log: `reservation_created`, `seat_added` action types
- Validation: DB CHECK constraint (1-28) + app-level layout.json
- FSM storage: permanent (no TTL), manual cleanup only

---

## Configuration (.env.example)

```env
VK_BOT_TOKEN=your_vk_bot_token
VK_GROUP_ID=your_group_id

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

DATABASE_URL=sqlite:///tickets.db

SEAT_PRICE=1500
LOG_LEVEL=INFO
```

---

## Project Structure

```
bot/
├── __init__.py
├── main.py              # Entry point
├── config.py            # Configuration loading
├── handlers/
│   ├── __init__.py
│   ├── reservation.py   # Reservation creation/editing handlers
│   └── commands.py      # /start, /help, /cancel handlers
├── fsm/
│   ├── __init__.py
│   ├── states.py        # FSM state definitions
│   └── storage.py       # Redis storage for FSM
├── keyboards.py         # Keyboard generators
├── messages.py          # Message templates
├── utils/
│   ├── __init__.py
│   ├── db.py            # Database integration
│   ├── seat_parser.py   # Seat input parser
│   ├── layout.py        # Hall layout loading
│   └── errors.py        # Error handling
└── tests/
    ├── __init__.py
    ├── test_seat_parser.py
    └── test_db_integration.py
```

---

## Next Phase

After Phase 1 completion:
- Phase 2: Main menu, seat deletion, reservation cancellation

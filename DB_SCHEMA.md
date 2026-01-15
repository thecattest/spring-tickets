# Схема SQL БД (черновик) — учет билетов на концерт

Документ описывает **предполагаемую** схему SQL-БД, исходя из текущих требований в `TZ.md`.

## 1) Предпосылки и принятые решения

- Событие/площадка/рассадка **одни** → отдельные таблицы `events/venues` не вводим (но при желании можно добавить позже без ломки домена).
- “Схема зала” и ограничения рядов/мест хранятся в JSON layout **вне БД** (файл/конфиг). БД хранит только факты занятости (бронь/оплата/резерв) и аудит.
- Валидация (существование ряда/места по layout) выполняется на уровне приложения, но базовые CHECK-ограничения (диапазоны) задаем и в БД.
- Нужно жестко предотвратить двойное занятие одного места → используем **единую таблицу занятости мест** `seat_assignments` с частичным уникальным индексом на активные назначения.
- Требуется полный аудит действий пользователей + системных событий (напоминания).

Ниже DDL ориентирован на **PostgreSQL** (из‑за частичных уникальных индексов).

## 2) Справочные типы (ENUM)

```sql
-- роли внутренних пользователей
CREATE TYPE user_role AS ENUM ('admin', 'seller');

-- состояние брони
CREATE TYPE reservation_state AS ENUM ('active', 'cancelled');

-- статус места (в рамках брони или резерва)
-- booked: забронировано (не оплачено)
-- paid: оплачено
-- reserved: резерв (под гостей)
CREATE TYPE seat_status AS ENUM ('booked', 'paid', 'reserved');
```

## 3) Таблицы

### 3.1 Пользователи системы (админ/билетер)

```sql
CREATE TABLE app_users (
  id              BIGSERIAL PRIMARY KEY,
  role            user_role NOT NULL,
  display_name    TEXT NOT NULL,

  -- если билетер тоже живет в VK, можно хранить связку
  vk_user_id      BIGINT,
  vk_profile_url  TEXT,

  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- ускоряет выборки по роли (например, рассылка напоминаний всем билетерам)
CREATE INDEX app_users_role_idx ON app_users(role);
-- чтобы один vk_user_id не был привязан к нескольким пользователям системы
CREATE UNIQUE INDEX app_users_vk_user_id_uniq ON app_users(vk_user_id) WHERE vk_user_id IS NOT NULL;
```

### 3.2 Покупатели (VK)

```sql
CREATE TABLE vk_users (
  id              BIGSERIAL PRIMARY KEY,
  vk_user_id      BIGINT NOT NULL UNIQUE,
  display_name    TEXT NOT NULL,
  profile_url     TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.3 Брони

`reservations.last_activity_at` — ключевое поле для напоминаний: **7 дней после последнего действия** по брони.

```sql
CREATE TABLE reservations (
  id                BIGSERIAL PRIMARY KEY,
  buyer_vk_user_id  BIGINT NOT NULL REFERENCES vk_users(id),
  sold_by_user_id   BIGINT NOT NULL REFERENCES app_users(id), -- кто оформил бронь

  state             reservation_state NOT NULL DEFAULT 'active',

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  cancelled_at      TIMESTAMPTZ
);

-- частые выборки "бронь покупателя"
CREATE INDEX reservations_buyer_idx ON reservations(buyer_vk_user_id);
-- для отчетов и напоминаний "мои продажи/мои должники"
CREATE INDEX reservations_sold_by_idx ON reservations(sold_by_user_id);
-- для выборки должников по последней активности
CREATE INDEX reservations_last_activity_idx ON reservations(last_activity_at);
```

## 3.A Рекомендуемый вариант (Вариант 2): единая таблица занятости мест (без `seat_locks`)

Это вариант без “дублирования информации о месте” между разными таблицами.

```sql
CREATE TABLE seat_assignments (
  id               BIGSERIAL PRIMARY KEY,

  -- координаты места (валидируются дополнительно по JSON layout)
  row_number       INT NOT NULL CHECK (row_number BETWEEN 1 AND 24),
  seat_number      INT NOT NULL CHECK (seat_number BETWEEN 1 AND 28),

  -- reserved используется для резерва; booked/paid — для брони
  status           seat_status NOT NULL,

  -- если место относится к брони, заполняется reservation_id
  reservation_id   BIGINT REFERENCES reservations(id) ON DELETE CASCADE,

  -- кто и когда сделал занятие/снятие
  created_by_user_id  BIGINT REFERENCES app_users(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  released_at      TIMESTAMPTZ,
  released_by_user_id BIGINT REFERENCES app_users(id),

  note             TEXT
);

-- Гарантирует: ровно одно активное назначение на место (в бронь/в резерв) в любой момент времени
CREATE UNIQUE INDEX seat_assignments_one_active_per_seat
  ON seat_assignments(row_number, seat_number)
  WHERE released_at IS NULL;

-- Ускоряет: "места этой брони" (день концерта, просмотр брони, отчеты)
CREATE INDEX seat_assignments_reservation_idx
  ON seat_assignments(reservation_id)
  WHERE reservation_id IS NOT NULL AND released_at IS NULL;

-- Ускоряет: поиск по месту (ряд/место), например на странице дня концерта
CREATE INDEX seat_assignments_row_seat_idx
  ON seat_assignments(row_number, seat_number)
  WHERE released_at IS NULL;
```

Примечания:
- **резерв** — строки `seat_assignments` со `status='reserved'` и `reservation_id IS NULL`
- **бронь** — строки `seat_assignments` со `status IN ('booked','paid')` и `reservation_id = ...`
- “свободно” — отсутствие активной строки (т.е. `released_at IS NOT NULL` или записи нет)

### 3.7 Оплаты (чеки)

Требования:
- хранить ссылку на сообщение с чеком, дату сообщения, кто отметил;
- оплата относится к конкретной брони и конкретному покупателю (VK);
- билетер указывает **какие именно места** оплачены этим чеком (не только количество).

```sql
CREATE TABLE payments (
  id               BIGSERIAL PRIMARY KEY,
  reservation_id   BIGINT NOT NULL REFERENCES reservations(id),
  recorded_by_user_id BIGINT NOT NULL REFERENCES app_users(id), -- кто отметил

  vk_message_url   TEXT NOT NULL,
  vk_message_ts    TIMESTAMPTZ NOT NULL,     -- дата отправки чека
  recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  note             TEXT
);

-- для просмотра оплат по конкретной брони
CREATE INDEX payments_reservation_idx ON payments(reservation_id);
-- для фин.отчетов/сортировки по дате чека
CREATE INDEX payments_vk_message_ts_idx ON payments(vk_message_ts);
```

Какие места оплачены этим чеком:

```sql
CREATE TABLE payment_seats (
  payment_id         BIGINT NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
  seat_assignment_id  BIGINT NOT NULL REFERENCES seat_assignments(id),
  PRIMARY KEY (payment_id, seat_assignment_id)
);

-- Гарантия: одно активное место не может быть "оплачено" двумя разными чеками
CREATE UNIQUE INDEX payment_seats_one_payment_per_seat
  ON payment_seats(seat_assignment_id);
```

Примечание:
- Покупатель для оплаты не хранится в `payments`, т.к. однозначно определяется через `payments.reservation_id → reservations.buyer_vk_user_id`.
- Проверка “чек переслан от того же VK-аккаунта, что и бронь” выполняется на уровне приложения сравнением отправителя чека с `reservations.buyer_vk_user_id`.

### 3.8 Расходы (админ)

```sql
CREATE TABLE expenses (
  id                 BIGSERIAL PRIMARY KEY,
  created_by_user_id BIGINT NOT NULL REFERENCES app_users(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- когда расход фактически произошел (день/время перевода денег),
  -- может отличаться от created_at (когда админ внес запись в систему)
  occurred_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  amount_rub         INT NOT NULL CHECK (amount_rub > 0),
  note               TEXT
);

-- для сортировки/фильтра по дате расхода в фин.отчете
CREATE INDEX expenses_occurred_at_idx ON expenses(occurred_at);
```

### 3.9 Чекапы финансов (проверено)

```sql
CREATE TABLE reconcile_checkpoints (
  id                 BIGSERIAL PRIMARY KEY,
  checked_by_user_id BIGINT NOT NULL REFERENCES app_users(id),
  checked_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  note               TEXT
);

-- быстро найти последний чекап и фильтровать "до/после него"
CREATE INDEX reconcile_checkpoints_checked_at_idx ON reconcile_checkpoints(checked_at);
```

### 3.10 Аудит-лог

```sql
CREATE TABLE audit_log (
  id            BIGSERIAL PRIMARY KEY,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  actor_type    TEXT NOT NULL CHECK (actor_type IN ('user', 'system')),
  actor_user_id BIGINT REFERENCES app_users(id),

  action_type   TEXT NOT NULL,      -- каталог типов действий уточняется позже
  entity_type   TEXT NOT NULL,      -- reservation/payment/expense/seat_assignment/...
  entity_id     TEXT,               -- строкой (на случай разных типов id)

  payload       JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- быстрая прокрутка/фильтрация по времени
CREATE INDEX audit_log_created_at_idx ON audit_log(created_at);
-- фильтр по типу действия
CREATE INDEX audit_log_action_type_idx ON audit_log(action_type);
-- фильтр "все события по сущности"
CREATE INDEX audit_log_entity_idx ON audit_log(entity_type, entity_id);
-- фильтр по пользователю (кто делал)
CREATE INDEX audit_log_actor_user_idx ON audit_log(actor_user_id);
```

## 4) Выводимые “статусы места”

Текущий статус конкретного места (ряд, место) определяется так:
- если есть активный `seat_assignments` (строка с `released_at IS NULL`) → статус равен `seat_assignments.status`:
  - `reserved` → **Резерв**
  - `booked` → **Бронь**
  - `paid` → **Оплачено**
- иначе → **Свободно**

Для “карты зала” дополнительно сводим к 2 состояниям:
- Свободно → “можно”
- любое другое → “нельзя”

## 5) Ключевые запросы (на уровне идеи)

### 5.1 “Должники” для напоминаний

Ищем активные брони продавца, где есть неоплаченные места, и с последней активности прошло ≥ 7 дней:

```sql
SELECT r.*
FROM reservations r
WHERE r.state = 'active'
  AND r.sold_by_user_id = $sellerId
  AND r.last_activity_at <= now() - interval '7 days'
  AND EXISTS (
    SELECT 1
    FROM seat_assignments sa
    WHERE sa.reservation_id = r.id
      AND sa.released_at IS NULL
      AND sa.status = 'booked'
  );
```

### 5.2 “День концерта”: поиск по имени или месту

- По имени: `JOIN vk_users` и фильтр по `vk_users.display_name ILIKE ...`
- По месту: фильтр по `seat_assignments.row_number` и `seat_assignments.seat_number`.

## 6) TODO / вопросы для уточнения (влияют на схему)

- Нужны ли “корректировки”/отмена оплаты как отдельная сущность (например `payment_reversals`) или достаточно аудит-лога?
- Как трактовать переход **Оплачено → Свободно** (админ “удалил оплату и бронь”): \n
  - это откат до брони и последующее снятие брони, или прямое освобождение места с особыми правами?


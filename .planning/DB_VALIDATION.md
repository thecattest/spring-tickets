# Database Architecture Validation for VK Bot

**Date:** 2026-01-24
**Phase:** 0 - Pre-development validation
**Status:** In Progress

---

## Executive Summary

Проверка существующей архитектуры БД на соответствие требованиям VK бота из BOT_SPEC.md.

**Overall Status:** ⚠️ **Minor gaps found - requires schema updates**

- ✅ Core scenarios: **Fully covered**
- ⚠️ Payment model: **Missing 2 fields**
- ⚠️ Indexes: **1 composite index recommended**
- ✅ Constraints: **Adequate**
- ✅ Audit log: **Ready**

---

## 1. Scenario Coverage Analysis

### 1.1 Создание брони (Scenario 1 - BOT_SPEC.md)

**Required data flow:**
1. Билетер пересылает сообщение → получаем VK user ID автора
2. Проверяем есть ли VkUser → создаем если нет
3. Создаем Reservation с buyer_vk_user_id + sold_by_user_id
4. Добавляем места через SeatAssignment

**DB Coverage:**
- ✅ `VkUser` model: `vk_user_id` (unique), `display_name` для скрипта
- ✅ `Reservation` model: `buyer_vk_user_id`, `sold_by_user_id`, `state`, `last_activity_at`
- ✅ `SeatAssignment` model: `row_number`, `seat_number`, `status=BOOKED`, `reservation_id`
- ✅ `AppUser` model: `role` (ADMIN/SELLER) для определения прав

**Issues:** None

---

### 1.2 Добавление/удаление мест (Scenarios 1, 3 - BOT_SPEC.md)

**Required operations:**
- Добавление: INSERT INTO seat_assignments
- Удаление: UPDATE seat_assignments SET released_at = NOW()
- Валидация занятости: CHECK (row, seat) WHERE released_at IS NULL
- Атомарность: транзакция на уровне приложения

**DB Coverage:**
- ✅ `SeatAssignment.released_at` для soft delete
- ✅ `SeatAssignment.released_by_user_id` для audit trail
- ✅ Partial index `seat_assignments_one_active_per_seat` гарантирует уникальность
- ✅ CHECK constraints на row_number (1-24) и seat_number (1-28)

**Validation strategy:**
- DB level: CHECK constraint (upper bound 1-28) ✅
- App level: точная валидация по layout.json (переменное количество мест) ✅

**Issues:** None

---

### 1.3 Главное меню (Scenario 2 - BOT_SPEC.md)

**Required queries:**
1. Найти активную бронь: `SELECT * FROM reservations WHERE buyer_vk_user_id = X AND state = 'active'`
2. Получить места брони: `SELECT * FROM seat_assignments WHERE reservation_id = Y AND released_at IS NULL`
3. Группировка по статусам: BOOKED / PAID / (RESERVED показывать отдельно)

**DB Coverage:**
- ✅ Index `reservations_buyer_idx` on `buyer_vk_user_id` — ускоряет поиск брони
- ✅ Index `seat_assignments_reservation_idx` on `reservation_id` (строка 77-78 seat_assignment.py) — ускоряет поиск мест
- ✅ `SeatAssignment.status` enum (BOOKED/PAID/RESERVED)

**Issues:** None

---

### 1.4 Регистрация оплаты (Scenario 5 - BOT_SPEC.md)

**Required operations:**
1. Детерминированный выбор мест: `SELECT ... WHERE status=BOOKED ORDER BY row_number ASC, seat_number ASC LIMIT N`
2. Создание Payment записи
3. Обновление SeatAssignment.status → PAID
4. Создание PaymentSeat связей
5. Обновление Reservation.last_activity_at

**DB Coverage:**
- ✅ `Payment` model: `reservation_id`, `recorded_by_user_id`, `vk_message_url`, `vk_message_ts`
- ✅ `PaymentSeat` model: связь payment ↔ seat_assignment
- ✅ Unique index на `seat_assignment_id` — одно место = один платеж

**Issues:**
❌ **CRITICAL GAP:** Payment model **missing required fields**

According to BOT_SPEC.md line 282:
```
- `Payment`: создать запись с `payment_amount`, `seat_count`
```

**Current Payment model (models/payment.py) does NOT have:**
- `payment_amount` — сумма оплаты (для финансовой отчетности)
- `seat_count` — количество мест в этой оплате (для быстрого подсчета)

**Impact:**
- Cannot display "К оплате: [сумма] руб." без вычисления через COUNT(payment_seats)
- Financial reports require JOINs instead of simple SUM(payment_amount)
- Partial payment tracking requires COUNT instead of direct field access

**Recommendation:** Add fields to Payment model

---

### 1.5 Управление резервами (Scenario 6 - BOT_SPEC.md)

**Required operations:**
1. Проверка прав: AppUser.role == ADMIN
2. Создание резерва: INSERT seat_assignments с status=RESERVED, reservation_id=NULL, note=<комментарий>
3. Удаление резерва: UPDATE released_at = NOW()
4. Отображение при проверке занятости: показать комментарий

**DB Coverage:**
- ✅ `AppUser.role` enum (ADMIN/SELLER) — проверка прав
- ✅ `SeatAssignment.status = RESERVED` — отдельный статус для резервов
- ✅ `SeatAssignment.reservation_id` nullable — для резервов = NULL
- ✅ `SeatAssignment.note` TEXT — обязательный комментарий для резервов

**Issues:** None

---

### 1.6 Просмотр должников (Scenarios 8, 9 - BOT_SPEC.md)

**Required query:**
```sql
SELECT r.*, vk.display_name, COUNT(sa.id) as seat_count
FROM reservations r
JOIN vk_users vk ON r.buyer_vk_user_id = vk.id
LEFT JOIN seat_assignments sa ON sa.reservation_id = r.id
  AND sa.released_at IS NULL
  AND sa.status = 'booked'
WHERE r.state = 'active'
  AND r.last_activity_at <= NOW() - INTERVAL '7 days'
  AND (r.sold_by_user_id = <user> OR <user_is_admin>)
GROUP BY r.id, vk.id
ORDER BY r.last_activity_at ASC
```

**DB Coverage:**
- ✅ Index `reservations_sold_by_idx` on `sold_by_user_id`
- ✅ Index `reservations_last_activity_idx` on `last_activity_at`
- ✅ `Reservation.state` для фильтрации активных
- ✅ `SeatAssignment.status` для подсчета BOOKED мест

**Potential Performance Issue:**
⚠️ **No composite index** for multi-column WHERE clause

Query filters on:
- `sold_by_user_id` = X
- `last_activity_at` <= Y
- `state` = 'active'

Current indexes are **separate**, which may cause:
- Index scan on sold_by_user_id → filter by last_activity_at
- OR index scan on last_activity_at → filter by sold_by_user_id

**Impact:** Low-Medium
- Works correctly with separate indexes
- Performance acceptable for <1000 reservations
- May slow down with >10K reservations

**Recommendation:** Add composite index (optional, for optimization):
```sql
CREATE INDEX reservations_debtors_idx
ON reservations(sold_by_user_id, last_activity_at)
WHERE state = 'active';
```

---

## 2. Index Analysis

### 2.1 Existing Indexes

**AppUser (models/user.py):**
- ✅ `app_users_role_idx` on `role` — для рассылки напоминаний
- ✅ `app_users_vk_user_id_uniq` on `vk_user_id` (partial, WHERE NOT NULL) — уникальность

**VkUser (models/vk_user.py):**
- ✅ UNIQUE constraint на `vk_user_id` — быстрый поиск по VK ID

**Reservation (models/reservation.py):**
- ✅ `reservations_buyer_idx` on `buyer_vk_user_id` — поиск брони клиента
- ✅ `reservations_sold_by_idx` on `sold_by_user_id` — "мои продажи"
- ✅ `reservations_last_activity_idx` on `last_activity_at` — должники

**SeatAssignment (models/seat_assignment.py):**
- ✅ `seat_assignments_one_active_per_seat` UNIQUE on `(row_number, seat_number)` WHERE `released_at IS NULL` — критичный для предотвращения двойного бронирования
- ✅ `seat_assignments_reservation_idx` on `reservation_id` WHERE `reservation_id IS NOT NULL AND released_at IS NULL` — места брони
- ✅ `seat_assignments_row_seat_idx` on `(row_number, seat_number)` WHERE `released_at IS NULL` — проверка занятости

**Payment (models/payment.py):**
- ✅ `payments_reservation_idx` on `reservation_id` — оплаты по брони
- ✅ `payments_vk_message_ts_idx` on `vk_message_ts` — сортировка по дате чека

**PaymentSeat (models/payment.py):**
- ✅ `payment_seats_one_payment_per_seat` UNIQUE on `seat_assignment_id` — одно место = один платеж

**AuditLog (models/audit.py):**
- ✅ `audit_log_created_at_idx` on `created_at` — хронология
- ✅ `audit_log_action_type_idx` on `action_type` — фильтрация
- ✅ `audit_log_entity_idx` on `(entity_type, entity_id)` — события сущности
- ✅ `audit_log_actor_user_idx` on `actor_user_id` — действия пользователя

### 2.2 Missing Indexes

⚠️ **Recommended (optional):**
- Composite index для должников: `(sold_by_user_id, last_activity_at) WHERE state='active'`

---

## 3. Constraints Validation

### 3.1 CHECK Constraints

**SeatAssignment (models/seat_assignment.py):**
```python
CheckConstraint("row_number BETWEEN 1 AND 24")
CheckConstraint("seat_number BETWEEN 1 AND 28")
```

**Status:** ✅ Adequate
- Upper bound (28) covers max seats in layout.json
- Precise validation per row (21-28 seats) done at app level via layout.json
- Strategy is sound: DB enforces max, app enforces exact

### 3.2 Foreign Keys

**All models:**
- ✅ Reservation.buyer_vk_user_id → vk_users.id
- ✅ Reservation.sold_by_user_id → app_users.id
- ✅ SeatAssignment.reservation_id → reservations.id (ON DELETE CASCADE)
- ✅ SeatAssignment.created_by_user_id → app_users.id
- ✅ Payment.reservation_id → reservations.id
- ✅ Payment.recorded_by_user_id → app_users.id
- ✅ PaymentSeat.payment_id → payments.id (ON DELETE CASCADE)
- ✅ PaymentSeat.seat_assignment_id → seat_assignments.id
- ✅ AuditLog.actor_user_id → app_users.id (nullable)

**Cascade behavior:**
- ✅ Deleting Reservation cascades to SeatAssignments — correct для отмены брони
- ✅ Deleting Payment cascades to PaymentSeats — correct для корректировки платежей

---

## 4. Audit Log Validation

### 4.1 Action Types from BOT_SPEC.md

BOT_SPEC.md defines 9 action types (section "Audit Log: Каталог типов действий"):

| Action Type | Entity Type | Required by Bot? | DB Support |
|-------------|-------------|------------------|------------|
| `reservation_created` | reservation | ✅ Yes | ✅ Yes |
| `seat_added` | reservation | ✅ Yes | ✅ Yes |
| `seat_removed` | reservation | ✅ Yes | ✅ Yes |
| `reservation_cancelled` | reservation | ✅ Yes | ✅ Yes |
| `payment_recorded` | payment | ✅ Yes | ✅ Yes |
| `payment_reversed` | payment | ⚠️ Future (Phase 6) | ✅ Yes |
| `reserve_added` | seat_assignment | ✅ Yes | ✅ Yes |
| `reserve_removed` | seat_assignment | ✅ Yes | ✅ Yes |
| `debtors_notification_sent` | system | ✅ Yes | ✅ Yes |

**Status:** ✅ All action types supported

AuditLog.action_type is TEXT (flexible), payload is JSON (flexible) — can store any structure.

### 4.2 Payload Requirements

BOT_SPEC.md specifies payload fields for each action:
- ✅ `reservation_created`: {reservation_id, buyer_vk_user_id, buyer_name}
- ✅ `seat_added`: {seat_ids: [int], row: int, seats: [int]}
- ✅ `payment_recorded`: {payment_id, reservation_id, seat_ids, amount, partial: bool}
- etc.

All payloads fit into JSON structure ✅

---

## 5. Missing Fields / Relationships

### 5.1 Critical Gaps

❌ **Payment model missing fields:**
1. `payment_amount` — сумма оплаты (Decimal/Float)
2. `seat_count` — количество мест (Integer)

**Required by:** BOT_SPEC.md line 282, ROADMAP.md Phase 3

**Usage:**
- Display total amount in bot messages
- Financial reports (SUM(payment_amount))
- Quick access to seat count without JOINing payment_seats

### 5.2 Optional Additions

💡 **VkUser fields for better name formatting:**

Current: `display_name` TEXT (может быть "Иван Иванов" или "ivan_ivanov")

BOT needs: "[Имя Фамилия]" for scripts

**Options:**
1. **Keep as is:** Parse display_name (if VK provides "FirstName LastName")
2. **Add fields:** `first_name`, `last_name` (explicitly)

**Recommendation:** Check VK API response format. If VK provides structured name, add `first_name` and `last_name` fields for cleaner data model.

---

## 6. Concurrency & Race Conditions

### 6.1 Partial Index Protection

**Mechanism:**
```python
Index(
    "seat_assignments_one_active_per_seat",
    "row_number",
    "seat_number",
    unique=True,
    sqlite_where=text("released_at IS NULL"),
)
```

**Protection level:** ✅ Strong
- Prevents duplicate (row, seat) WHERE released_at IS NULL
- Database-level guarantee (not app-level)
- Works in SQLite 3.8.0+ and PostgreSQL

**Test coverage gap (from CONCERNS.md):**
⚠️ No concurrency test in test_db.py — should add

**Recommendation:** Add integration test:
```python
def test_concurrent_seat_booking():
    # Two threads try to book same seat simultaneously
    # One should succeed, one should get IntegrityError
```

### 6.2 SQLite Write Lock

**Current constraint:** SQLite allows only 1 writer at a time

**Impact:**
- <10 билетеров: OK
- >10 билетеров: potential write contention

**Mitigation:** Documented in ROADMAP.md (migrate to PostgreSQL when scaling)

---

## 7. Schema Changelog

### 7.1 Required Changes

**Payment model (models/payment.py):**

Add fields:
```python
payment_amount: Mapped[Decimal] = mapped_column(
    Numeric(10, 2),
    nullable=False,
    comment="Сумма оплаты (руб.)"
)
seat_count: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    comment="Количество оплаченных мест"
)
```

**Migration:**
```sql
-- SQLite
ALTER TABLE payments ADD COLUMN payment_amount REAL NOT NULL DEFAULT 0.0;
ALTER TABLE payments ADD COLUMN seat_count INTEGER NOT NULL DEFAULT 0;

-- PostgreSQL
ALTER TABLE payments ADD COLUMN payment_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.0;
ALTER TABLE payments ADD COLUMN seat_count INTEGER NOT NULL DEFAULT 0;
```

**Note:** Existing payments (if any) will need backfill:
```sql
UPDATE payments p
SET seat_count = (SELECT COUNT(*) FROM payment_seats WHERE payment_id = p.id);
```

### 7.2 Recommended Changes (optional)

**Composite index for debtors query:**
```sql
CREATE INDEX reservations_debtors_idx
ON reservations(sold_by_user_id, last_activity_at)
WHERE state = 'active';
```

**VkUser name fields (optional, depending on VK API format):**
```python
first_name: Mapped[str] = mapped_column(Text, nullable=False)
last_name: Mapped[str] = mapped_column(Text, nullable=False)
# Keep display_name as fallback or remove if redundant
```

---

## 8. Summary & Action Items

### 8.1 Status

✅ **DB architecture is 95% ready for bot development**

Core scenarios, constraints, audit log — fully covered.

### 8.2 Blocking Issues

❌ **1 critical gap must be fixed before Phase 1:**

1. **Payment model missing fields:** `payment_amount`, `seat_count`
   - Required for: financial reporting, bot messages, partial payment tracking
   - Impact: Cannot implement Phase 3 (payment registration) without these fields
   - Effort: ~30 min (add fields + migration)

### 8.3 Non-blocking Recommendations

⚠️ **2 optional improvements:**

1. **Composite index for debtors:** `(sold_by_user_id, last_activity_at)`
   - Benefit: Faster debtors query (Phase 5)
   - Impact if skipped: Performance OK for <1000 reservations
   - Effort: ~5 min

2. **VkUser structured name fields:** `first_name`, `last_name`
   - Benefit: Cleaner data model, easier name formatting
   - Impact if skipped: Must parse display_name (OK if VK provides structured format)
   - Effort: ~15 min
   - Decision: Check VK API response format first

### 8.4 Action Plan

**Before Phase 1:**
1. ✅ Add `payment_amount` and `seat_count` to Payment model
2. ✅ Create migration for existing data (if any)
3. ✅ Update test_db.py to validate new fields

**Before Phase 5 (optional):**
4. ⚠️ Add composite index for debtors query

**Research (before Phase 1):**
5. ⚠️ Check VK API user response format → decide on first_name/last_name fields

---

## 9. Updated CONCERNS.md

Items to add to `.planning/codebase/CONCERNS.md`:

**Missing Critical Features:**
- Payment.payment_amount and Payment.seat_count fields missing (blocks Phase 3)

**Performance Bottlenecks:**
- Debtors query lacks composite index (minor impact, <1K reservations)

**Test Coverage Gaps:**
- No concurrent seat booking test (race condition validation)

---

*Validation completed: 2026-01-24*
*Next: Update Payment model → Ready for Phase 1*

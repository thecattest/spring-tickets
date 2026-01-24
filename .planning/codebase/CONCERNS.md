# Codebase Concerns

**Analysis Date:** 2026-01-24

## Tech Debt

**Incomplete Audit Log Specification:**
- Issue: Audit log schema defined but action types and required payload fields remain unspecified ("каталог типов действий уточняется позже")
- Files: `models/audit.py`, `DB_SCHEMA.md` (section 3.10, line 227)
- Impact: Cannot implement audit logging correctly until action type catalog is finalized; risk of inconsistent payload formats across different operations
- Fix approach: Complete the action type catalog in TZ.md section 10 with: (1) complete list of all action types, (2) required and optional payload fields for each, (3) examples of payloads for complex operations (e.g., partial payment, payment reversal)

**Uncertain Payment Reversal Mechanism:**
- Issue: Two competing design approaches not decided: create "payment_reversals" table vs use audit log; also unclear if reversal should go "Оплачено → Бронь" or "Оплачено → Свободно"
- Files: `DB_SCHEMA.md` (section 6, lines 285-287), `TZ.md` (section 6.3, line 261)
- Impact: Schema needs revision if reversal table is chosen; affects financial reporting aggregations; may cause data inconsistency if approach changes mid-implementation
- Fix approach: Document decision matrix comparing both approaches (query complexity, auditability, financial reconciliation difficulty); implement chosen approach and update Payment model schema accordingly

**Incomplete Seat Status Transition Rules:**
- Issue: Payloads section (TZ.md 11) defines only basic transitions; edge cases not covered (e.g., what happens if admin deletes a payment and the associated reservation is also deleted; state of Reservation.state field after all seats are released)
- Files: `TZ.md` (section 11, lines 501-520)
- Impact: Implementation may create invalid state combinations; no clear path for cleanup operations
- Fix approach: Expand transition rules document with: (1) state consistency invariants, (2) orphaned record cleanup procedures, (3) cascading delete behavior specification

**Missing Payment Cancellation/Reversal Audit Trail:**
- Issue: Payment reversal (admin-only) requires logging but no clear specification for what payload fields should capture the reversal reason and link to original payment
- Files: `models/audit.py`, `TZ.md` (section 6.3, line 261-263)
- Impact: Cannot properly audit and trace financial corrections; admin actions on payments lack accountability
- Fix approach: Add audit payload schema for payment reversal that includes: original_payment_id, reversal_reason, affected_seat_ids

## Known Bugs

**SQLite Type Mapping Limitations:**
- Symptoms: JSON vs JSONB not distinguished in SQLite; BigInteger mapped to Integer (potential overflow for very large IDs)
- Files: `SQLITE_MIGRATION.md` (section 1, lines 8-9)
- Trigger: Extended deployment with high volume data or PostgreSQL migration
- Workaround: None in current SQLite; PostgreSQL migration required for full type support
- Note: This is documented as MVP limitation, acceptable for initial phase

**Partial Index Support Assumption:**
- Symptoms: Code assumes SQLite 3.8.0+ for partial index support (sqlite_where clauses)
- Files: `SQLITE_MIGRATION.md` (line 18), `models/seat_assignment.py` (lines 72, 78, 85), `models/user.py` (line 37)
- Trigger: Deployment on systems with SQLite < 3.8.0 (unlikely but possible in legacy environments)
- Workaround: None; would require application-level validation for uniqueness
- Impact: Allows duplicate seat assignments if index fails silently

## Security Considerations

**Missing Payment Authorization Validation:**
- Risk: Code does not explicitly validate that the VK user sending a payment check is the same as the reservation's buyer
- Files: `models/payment.py`, `README_MODELS.md` (section important remarks, line 202)
- Current mitigation: Documented as "выполняется на уровне приложения" (application level) but no validation code visible
- Recommendations: (1) Implement explicit check in payment acceptance flow, (2) Log both expected and actual payment sender in audit log, (3) Add test case in test_db.py for cross-buyer payment attempt

**Missing Rate Limiting on Seat Bookings:**
- Risk: No rate limiting on seat assignment operations; malicious user could rapidly create/delete bookings (denial of service)
- Files: All seat operation endpoints (not yet implemented)
- Current mitigation: None documented
- Recommendations: (1) Implement per-user rate limiting (e.g., max 10 seat operations per minute), (2) Add monitoring alerts for suspicious patterns, (3) Consider transaction locking strategy during concurrent booking attempts

**Incomplete VK Authentication Context:**
- Risk: System relies on VK account verification but no specification of how VK tokens/sessions are validated
- Files: None (VK bot implementation not yet started)
- Current mitigation: Out of scope for current planning phase
- Recommendations: When implementing VK bot, document: (1) token validation approach, (2) session timeout, (3) re-authentication flow for long operations

## Performance Bottlenecks

**Potential N+1 Query on Seat Status Aggregation:**
- Problem: Day concert page needs to aggregate seat statuses per reservation; naive query could load each reservation's seats separately
- Files: Not yet implemented; concern from `TZ.md` section 5.2
- Cause: No batch loading strategy documented
- Improvement path: (1) Implement eager loading with session.options(joinedload), (2) Aggregate seat counts in SQL (SELECT ... GROUP BY), (3) Cache results with 30-second TTL

**Debtors Report Query Complexity:**
- Problem: "Должники" (debtors) query filters by sold_by_user_id + last_activity_at + state; no composite index optimization
- Files: `DB_SCHEMA.md` (section 5.1, lines 263-276), `README_MODELS.md` (section примеры запросов, lines 149-171), `DB_VALIDATION.md` (section 1.6)
- Cause: Query uses WHERE sold_by_user_id = X AND last_activity_at <= Y AND state = 'active'; separate indexes may require double scan
- Impact: Low-Medium (works correctly, performance OK for <1000 reservations; may slow down with >10K)
- Improvement path: (1) Add composite index: `CREATE INDEX reservations_debtors_idx ON reservations(sold_by_user_id, last_activity_at) WHERE state='active'`, (2) Profile with EXPLAIN PLAN before optimization
- Priority: **Low** - optional optimization for Phase 5

**Audit Log Query Performance with Large Datasets:**
- Problem: Audit log will grow rapidly; filtering by entity_id with text comparison is slow
- Files: `models/audit.py` (lines 37-40), `TZ.md` (section 5.3, lines 219-225)
- Cause: entity_id stored as TEXT; no numeric index; payload stored as JSON (requires parsing)
- Improvement path: (1) Split entity_id into entity_type_id + numeric ID, (2) Add composite index (entity_type, entity_id, created_at), (3) Consider archiving old audit records quarterly

## Fragile Areas

**SeatAssignment Partial Index Uniqueness (SQLite-specific):**
- Files: `models/seat_assignment.py` (lines 64-73)
- Why fragile: Partial index syntax differs between SQLite and PostgreSQL; migration will break this constraint without code review
- Safe modification: When refactoring, validate that unique constraint is enforced by DB, not application logic
- Test coverage: `test_db.py` has basic uniqueness test (line 182) but doesn't cover partial index edge cases (e.g., releasing then rebooking same seat)

**Reservation.last_activity_at Manual Updates:**
- Files: `models/reservation.py` (lines 33-36)
- Why fragile: Requires application to manually update timestamp on every operation (add/remove seat, payment, cancellation); easy to forget
- Safe modification: Implement database trigger for auto-update on INSERT/UPDATE to seat_assignments/payments with reservation_id, or wrap all operations in transaction with explicit update
- Test coverage: No test validates that last_activity_at actually updates across all operations

**Payment Status Tracking Without Explicit Status Field:**
- Files: `models/payment.py`, `models/seat_assignment.py`
- Why fragile: Payment "status" (active/cancelled/reversed) inferred from presence of PaymentSeat record and SeatAssignment.released_at; no explicit payment.is_cancelled field
- Safe modification: Add explicit `Payment.is_cancelled` BOOLEAN field or `Payment.cancelled_at` TIMESTAMPTZ to clarify state
- Test coverage: test_db.py creates payment but doesn't test payment cancellation scenarios

**Multiple Concurrent Seat Modifications:**
- Files: `models/seat_assignment.py` (lines 64-73 partial index enforcement)
- Why fragile: Relies on unique partial index to prevent duplicate bookings under concurrent writes; SQLite has coarse-grained locking (entire database), but competing writes may still cause race conditions
- Safe modification: Implement pessimistic row-level locking: SELECT ... FOR UPDATE on seat_assignments before modification
- Test coverage: No concurrent modification test in test_db.py

## Scaling Limits

**SQLite Concurrency Ceiling:**
- Current capacity: SQLite allows multiple readers but only one writer at a time
- Limit: System cannot handle >10 simultaneous ticketers making bookings during peak hours (e.g., opening day)
- Scaling path: (1) Migrate to PostgreSQL when VK bot goes live, (2) Set up connection pooling, (3) Implement optimistic locking (version numbers) if pessimistic locking becomes bottleneck

**Audit Log Growth:**
- Current capacity: Assuming 3 seat operations + 1 payment operation per reservation = ~4000 ops × 4 entries = 16K audit records for 1000 sales
- Limit: Audit queries become slow after ~1 million records (months of operation); full text search on entity_id becomes prohibitive
- Scaling path: (1) Archive old audit logs to separate read-only tables quarterly, (2) Implement time-series database for high-volume event data (ClickHouse), (3) Add denormalized analytics table for aggregated metrics

**Financial Report Aggregation Complexity:**
- Current capacity: Day concert report (section 5.2) with 1000 reservations should execute in <1 second with current indexes
- Limit: Adding filters (time range, seller, search text) may cause table scan; no materialized view for common report combinations
- Scaling path: (1) Create materialized views for common reports (payments_by_day, revenue_by_seller), (2) Implement incremental aggregation (store running totals), (3) Cache reports at application layer with 5-minute TTL

## Dependencies at Risk

**SQLite → PostgreSQL Migration Path Uncertain:**
- Risk: Code contains numerous sqlite_where() clauses in indexes; schema uses Integer instead of BigInteger
- Files: `SQLITE_MIGRATION.md` (section 4), `models/seat_assignment.py` (lines 72, 78, 85), `models/user.py` (line 37), `models/payment.py` (lines 45, 47)
- Impact: Migration will require: (1) refactor index definitions, (2) change Integer → BigInteger, (3) validate all PRAGMA settings (foreign_keys, etc.)
- Migration plan: (1) Document exact migration steps before going live, (2) Create parallel PostgreSQL database for staging, (3) Test full data export/import, (4) Plan downtime window for switchover

**SQLAlchemy 2.0+ Compatibility:**
- Risk: Code uses legacy mapped_column syntax; if dependencies force upgrade to future SQLAlchemy version, syntax may change
- Files: All models in `models/` directory
- Impact: Database initialization may fail; ORM operations may raise deprecation warnings
- Mitigation: (1) Lock SQLAlchemy to >=2.0,<3.0 in requirements.txt, (2) Monitor SQLAlchemy releases quarterly, (3) Plan upgrade path when 3.0 is announced

## Missing Critical Features

**Payment Model Missing Required Fields (CRITICAL):**
- Problem: Payment model lacks `payment_amount` (Decimal) and `seat_count` (Integer) fields required by VK bot
- Files: `models/payment.py`, `BOT_SPEC.md` (line 282), `ROADMAP.md` Phase 3
- Impact: Cannot implement payment registration (Phase 3); financial reports require complex JOINs; bot cannot display payment amounts
- Blocks: Phase 3 development (payment recording and script generation)
- Fix approach: Add fields to Payment model with migration; backfill existing payments if any
- Priority: **CRITICAL** - must fix before Phase 1 starts

**No Soft Delete / Archive Strategy:**
- Problem: Deleting reservations cascades to SeatAssignments (line 43 in reservation.py uses ondelete="CASCADE"); no way to view historical data after cancellation
- Blocks: Financial audits, dispute resolution with customers, trend analysis
- Implementation gap: Add soft_deleted_at field to Reservation and SeatAssignment; modify queries to exclude soft-deleted records by default

**No Conflict Detection for Overlapping Edits:**
- Problem: If two sellers attempt to book same seat simultaneously, one will fail with integrity error; no user-friendly conflict resolution
- Blocks: Day-of-event ticketing workflow when multiple sellers work simultaneously
- Implementation gap: Add optimistic locking (version field) to SeatAssignment; catch conflict exceptions and return list of conflicting seats to user for retry

**No Batch Operation Support:**
- Problem: Adding 10 seats requires 10 separate SeatAssignment inserts; no batch API
- Blocks: Day-concert page loading (N+1 query problem); slow VK bot response times
- Implementation gap: Create transaction wrapper for bulk operations; refactor seat addition to use single INSERT ... SELECT where possible

**No Automatic Debtors Notification System:**
- Problem: TZ.md section 8 requires sending debtors list every 3 days; no scheduled job framework
- Blocks: Debtors notifications feature
- Implementation gap: Add APScheduler or Celery for recurring tasks; implement notification logging in audit table

**No Payment Reversal Reconciliation Report:**
- Problem: When admin reverses payment, balanace aggregates need recalculation; no verification that sums still match audit trail
- Blocks: Financial reconciliation workflows
- Implementation gap: Add aggregate verification query; create reconciliation report showing payments, reversals, and net totals

## Test Coverage Gaps

**No Concurrency/Race Condition Testing:**
- What's not tested: Simultaneous seat booking attempts; payment recording under concurrent modifications
- Files: `test_db.py` (single-threaded only), `DB_VALIDATION.md` (section 6.1)
- Risk: Partial index uniqueness `seat_assignments_one_active_per_seat` provides DB-level protection, but not tested under concurrent load
- Priority: **High** - must test before VK bot launch
- Test scenario: Two threads attempt to book same (row, seat) simultaneously → one succeeds, one gets IntegrityError

**No Edge Case Testing for Seat Status Transitions:**
- What's not tested: (1) Release seat that is already released, (2) Mark as PAID when status is RESERVED, (3) Delete reservation with mixed BOOKED/PAID statuses
- Files: `test_db.py` (lines 156-167 check counts but not edge cases)
- Risk: Unknown behavior on invalid transitions
- Priority: **High** - affects data integrity

**No Payment Partial Scenarios:**
- What's not tested: (1) Partial payment (2 of 3 seats), (2) Reversal of partial payment, (3) Second payment covering remaining seats
- Files: `test_db.py` (lines 101-109 do test partial payment but not reversal)
- Risk: Financial data corruption if reversal logic is wrong
- Priority: **High** - affects financial reporting

**No Reservation Lifecycle Testing:**
- What's not tested: (1) Create → add seats → remove seats → cancel → try to add more, (2) last_activity_at update on various operations, (3) Debtors query result accuracy
- Files: `test_db.py` lacks complex multi-step workflows
- Risk: Business logic bugs in reservation state machine
- Priority: **Medium** - affects workflow correctness

**No Audit Log Verification:**
- What's not tested: (1) Audit log format validation, (2) Payload completeness for each operation type, (3) Audit trail integrity after cascading deletes
- Files: `test_db.py` (lines 126-138 create audit record but don't verify payload structure)
- Risk: Incomplete audit trail makes troubleshooting impossible
- Priority: **Medium** - affects compliance

**No Database Constraint Validation:**
- What's not tested: (1) CHECK constraints on row_number/seat_number, (2) Partial index uniqueness under edge cases, (3) Referential integrity with cascade deletes
- Files: `test_db.py` (line 182 tests basic uniqueness but not constraint completeness)
- Risk: Invalid data slips into database
- Priority: **Low** - database constraints should catch this, but explicit tests are safer

## Planning Uncertainties

**JSON Layout Schema Not Finalized:**
- Issue: TZ.md section 5.1.1 shows "черновой формат" (draft format) for layout.json; actual structure not implemented
- Files: `TZ.md` (lines 130-154)
- Blocks: Cannot implement seat validation, seat layout rendering, or bot responses until layout schema is final
- Resolution needed: Finalize layout.json schema; decide on row number representation (string vs int); define aisle/gap structure precisely

**Debtors Notification Time and Frequency TBD:**
- Issue: TZ.md section 8 says "вечером (уточнить)" and "1 раз в трое суток вечером (время будет задано позже)"
- Files: `TZ.md` (lines 457, 539)
- Blocks: Cannot implement scheduler until time is specified
- Resolution needed: Confirm exact time (e.g., 20:00 Moscow time) and frequency (every 3 days or daily); document timezone handling

**Audit Log Action Type Catalog Missing:**
- Issue: TZ.md section 10 lists operations but "точные фильтры будут описаны отдельно (позже)"
- Files: `TZ.md` (line 304)
- Blocks: Cannot implement audit filtering UI or API until action types are enumerated
- Resolution needed: Create exhaustive list of action_type values with examples (e.g., "reservation_created", "seat_added", "payment_recorded", "payment_reversed")

**Partial Payment Default Behavior Uncertain:**
- Issue: TZ.md section 6.3.1 asks whether deterministic "by order" rule is sufficient or if exact seat selection is required
- Files: `TZ.md` (lines 274, 265-272)
- Blocks: Cannot implement payment recording until this is decided
- Resolution needed: Confirm whether bot should: (1) automatically select first N unbooked seats, or (2) ask user to specify exact seat list for each partial payment

**Payment Correction Approach Not Chosen:**
- Issue: DB_SCHEMA.md section 6 asks whether to use separate payment_reversals table or payment.status field
- Files: `DB_SCHEMA.md` (lines 285-287)
- Blocks: Schema needs finalization before implementation
- Resolution needed: Compare both approaches; choose one and update schema

**Cascade Delete Behavior for Oплачено → Свободно:**
- Issue: When admin reverses payment and deletes reservation, unclear if seat goes → BOOKED or → RELEASED (freed)
- Files: `DB_SCHEMA.md` (lines 286-287)
- Blocks: Cannot implement payment reversal without clarity
- Resolution needed: Document precise state transitions with specific examples

**VK Bot API Integration Strategy:**
- Issue: No specification of how bot interacts with system (direct DB access vs HTTP API vs message queue)
- Files: Not yet planned
- Blocks: Cannot design bot until integration pattern is clear
- Resolution needed: Decide: (1) bot reads/writes directly to SQLite or PostgreSQL, (2) bot calls HTTP API endpoints, (3) bot publishes events to queue for async processing

---

*Concerns audit: 2026-01-24*

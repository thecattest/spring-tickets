-- Migration: Add payment_amount and seat_count to payments table
-- Date: 2026-01-24
-- Reason: Required for VK bot financial reporting and payment tracking

-- SQLite version
-- Note: SQLite does NOT support adding columns with NOT NULL and no DEFAULT in existing tables
-- So we add with DEFAULT, then update if needed

-- Add payment_amount column (default 0.0 for existing rows)
ALTER TABLE payments ADD COLUMN payment_amount REAL NOT NULL DEFAULT 0.0;

-- Add seat_count column (default 0 for existing rows)
ALTER TABLE payments ADD COLUMN seat_count INTEGER NOT NULL DEFAULT 0;

-- Backfill seat_count for existing payments (if any exist)
-- This calculates the count from payment_seats junction table
UPDATE payments
SET seat_count = (
    SELECT COUNT(*)
    FROM payment_seats
    WHERE payment_seats.payment_id = payments.id
)
WHERE EXISTS (
    SELECT 1 FROM payment_seats WHERE payment_seats.payment_id = payments.id
);

-- Note: payment_amount cannot be automatically backfilled
-- If there are existing payments, amount must be calculated manually:
-- payment_amount = seat_count * SEAT_PRICE (from config)
-- Run this after migration if needed:
-- UPDATE payments SET payment_amount = seat_count * <SEAT_PRICE> WHERE payment_amount = 0.0;

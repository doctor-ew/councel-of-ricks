-- Migration: 002_add_message_truth_score.sql
-- Ticket: GH-8 — Truth-O-Meter UI
-- Adds a deterministic 0-100 truth score column to the messages table.
--
-- The score is computed by the Arbiter from existing per-message inputs
-- (contradiction / unsupported flags + per-fact confidence). Persisted
-- on the message row so a session refresh shows the latest computed value
-- instead of a 100% default.
--
-- Nullable on purpose: historical rows (persisted before this column
-- existed) stay NULL and the frontend renders them as a neutral
-- "no score yet" state — NOT as 100. Do not back-fill.
--
-- Idempotent via IF NOT EXISTS so re-applying is safe.

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS truth_score INTEGER NULL;

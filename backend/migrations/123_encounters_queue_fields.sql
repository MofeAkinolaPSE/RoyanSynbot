-- Migration 123: Add queue management fields to royan_encounters
-- Enables: queue ticket numbers (e.g. OPD-001), nurse assessment step,
--          doctor call tracking, and consulting room assignment.

ALTER TABLE public.royan_encounters
  ADD COLUMN IF NOT EXISTS queue_number    TEXT,
  ADD COLUMN IF NOT EXISTS called_at       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS nurse_done_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS consulting_room VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_royan_encounters_queue_number
  ON public.royan_encounters(queue_number)
  WHERE external_source IS NULL;

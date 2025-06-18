-- Add admin_notes column to tickets table
-- Run this SQL in your Supabase SQL Editor

ALTER TABLE tickets 
ADD COLUMN IF NOT EXISTS admin_notes TEXT DEFAULT '';

-- Update existing tickets to have empty admin_notes if they don't have it
UPDATE tickets 
SET admin_notes = '' 
WHERE admin_notes IS NULL;

-- Verify the column was added
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'tickets' AND column_name = 'admin_notes';

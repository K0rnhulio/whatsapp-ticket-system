-- Migration script to update existing Supabase tables for voice/media support
-- Run this in your Supabase SQL Editor if you already have tables created

-- First, let's check if the columns exist and add them if they don't
DO $$
BEGIN
    -- Add message_type column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='message_type') THEN
        ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'text' CHECK (message_type IN ('text', 'audio', 'image', 'document', 'sticker', 'video'));
    END IF;
    
    -- Add file_url column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='file_url') THEN
        ALTER TABLE messages ADD COLUMN file_url TEXT;
    END IF;
    
    -- Add file_name column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='file_name') THEN
        ALTER TABLE messages ADD COLUMN file_name TEXT;
    END IF;
    
    -- Add file_size column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='file_size') THEN
        ALTER TABLE messages ADD COLUMN file_size INTEGER;
    END IF;
    
    -- Add duration column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='duration') THEN
        ALTER TABLE messages ADD COLUMN duration INTEGER;
    END IF;
    
    -- Add mime_type column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='mime_type') THEN
        ALTER TABLE messages ADD COLUMN mime_type TEXT;
    END IF;
    
    -- Add metadata column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='messages' AND column_name='metadata') THEN
        ALTER TABLE messages ADD COLUMN metadata JSONB;
    END IF;
    
    -- Make text column nullable (it was NOT NULL before)
    ALTER TABLE messages ALTER COLUMN text DROP NOT NULL;
END $$;

-- Create voice_transcriptions table if it doesn't exist
CREATE TABLE IF NOT EXISTS voice_transcriptions (
  id SERIAL PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  transcription_text TEXT,
  confidence_score DECIMAL(3,2), -- 0.00 to 1.00
  language_code TEXT DEFAULT 'en',
  transcription_service TEXT, -- e.g., 'openai-whisper', 'google-speech'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(message_id) -- One transcription per message
);

-- Add new indexes
CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(message_type);
CREATE INDEX IF NOT EXISTS idx_voice_transcriptions_message_id ON voice_transcriptions(message_id);

-- Create the view for messages with transcriptions
CREATE OR REPLACE VIEW messages_with_transcriptions AS
SELECT 
    m.*,
    vt.transcription_text,
    vt.confidence_score,
    vt.language_code,
    vt.transcription_service
FROM messages m
LEFT JOIN voice_transcriptions vt ON m.id = vt.message_id;

-- Update any existing messages to have message_type = 'text'
UPDATE messages SET message_type = 'text' WHERE message_type IS NULL;

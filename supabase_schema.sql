-- WhatsApp Ticketing System Database Schema for Supabase

-- Create tickets table
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  sender_id TEXT NOT NULL,
  sender_name TEXT,
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create messages table (updated to support different message types)
CREATE TABLE IF NOT EXISTS messages (
  id SERIAL PRIMARY KEY,
  ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  author TEXT NOT NULL,
  message_type TEXT DEFAULT 'text' CHECK (message_type IN ('text', 'audio', 'image', 'document', 'sticker', 'video')),
  text TEXT, -- For text messages and transcriptions
  file_url TEXT, -- For media files (voice, images, documents)
  file_name TEXT, -- Original filename
  file_size INTEGER, -- File size in bytes
  duration INTEGER, -- For audio/video files (in seconds)
  mime_type TEXT, -- MIME type of the file
  metadata JSONB, -- Additional metadata (e.g., transcription status, file info)
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create voice_transcriptions table for storing transcription results
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

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_tickets_sender_id ON tickets(sender_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_messages_ticket_id ON messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(message_type);
CREATE INDEX IF NOT EXISTS idx_voice_transcriptions_message_id ON voice_transcriptions(message_id);

-- Create updated_at trigger for tickets table
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tickets_updated_at 
    BEFORE UPDATE ON tickets 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Create a view for messages with transcriptions (useful for queries)
CREATE OR REPLACE VIEW messages_with_transcriptions AS
SELECT 
    m.*,
    vt.transcription_text,
    vt.confidence_score,
    vt.language_code,
    vt.transcription_service
FROM messages m
LEFT JOIN voice_transcriptions vt ON m.id = vt.message_id;

-- Insert some sample data (optional)
-- This will help test the migration from JSON to database
-- You can remove this section if you don't want sample data

-- Example ticket
-- INSERT INTO tickets (id, sender_id, sender_name, status, created_at) 
-- VALUES ('T1', '123456789@c.us', 'Test User', 'open', NOW());

-- Example text message
-- INSERT INTO messages (ticket_id, author, message_type, text, timestamp) 
-- VALUES ('T1', 'System', 'text', 'Thank you for contacting us! Your ticket ID is #T1. An agent will be with you shortly.', NOW());

-- Example voice message
-- INSERT INTO messages (ticket_id, author, message_type, text, file_url, duration, mime_type, timestamp) 
-- VALUES ('T1', 'User', 'audio', '[Voice Message]', 'https://example.com/voice.ogg', 15, 'audio/ogg', NOW());

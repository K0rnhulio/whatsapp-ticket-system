# WhatsApp Ticket System with Web Dashboard

A complete WhatsApp ticketing system built with Flask, featuring a web-based dashboard for agents to manage customer support tickets, send messages, files, and voice recordings.

## 🚀 Features

### Core Functionality
- **WhatsApp Integration** - Receive messages via Green API webhook
- **Ticket Management** - Auto-create, track, and close tickets
- **Multi-Channel Interface** - Web dashboard and terminal access
- **Database Persistence** - Supabase with JSON backup

### Web Dashboard
- **Text Replies** - Send messages to customers
- **File Uploads** - Send images, documents, videos (up to 100MB)
- **Voice Messages** - Browser recording with MP3 conversion for WhatsApp compatibility
- **Ticket Overview** - Filter by status, view message history
- **Real-time Updates** - Auto-refresh every 30 seconds

### Message Types Supported
- ✅ Text messages
- ✅ Voice messages (with transcription support)
- ✅ Images (JPG, PNG, GIF, WebP)
- ✅ Videos (MP4, AVI, MOV, etc.)
- ✅ Documents (PDF, DOC, etc.)

## 🛠️ Technology Stack

- **Backend**: Flask (Python)
- **Database**: Supabase (PostgreSQL)
- **WhatsApp API**: Green API
- **Frontend**: Bootstrap 5, JavaScript
- **Audio Processing**: FFmpeg
- **File Storage**: Temporary local storage

## 📋 Prerequisites

- Python 3.8+
- FFmpeg (for audio conversion)
- Green API account
- Supabase account
- ngrok (for webhook exposure)

## 🔧 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/whatsapp-ticket-system.git
   cd whatsapp-ticket-system
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg**
   - Download from [FFmpeg official site](https://ffmpeg.org/download.html)
   - Add to system PATH

4. **Set up environment variables**
   Create a `.env` file or set environment variables:
   ```
   GREEN_API_INSTANCE_ID=your_instance_id
   GREEN_API_TOKEN_INSTANCE=your_token
   SUPABASE_URL=your_supabase_url
   SUPABASE_ANON_KEY=your_supabase_key
   ```

5. **Set up Supabase database**
   Run the SQL schema in your Supabase dashboard:
   ```sql
   -- Create tickets table
   CREATE TABLE tickets (
       id TEXT PRIMARY KEY,
       sender_id TEXT NOT NULL,
       sender_name TEXT,
       status TEXT DEFAULT 'open',
       created_at TIMESTAMP DEFAULT NOW(),
       updated_at TIMESTAMP DEFAULT NOW()
   );

   -- Create messages table
   CREATE TABLE messages (
       id SERIAL PRIMARY KEY,
       ticket_id TEXT REFERENCES tickets(id),
       author TEXT NOT NULL,
       text TEXT,
       message_type TEXT DEFAULT 'text',
       file_url TEXT,
       file_name TEXT,
       file_size INTEGER,
       mime_type TEXT,
       duration INTEGER,
       timestamp TIMESTAMP DEFAULT NOW()
   );

   -- Create transcriptions table (for future AI features)
   CREATE TABLE transcriptions (
       id SERIAL PRIMARY KEY,
       message_id INTEGER REFERENCES messages(id),
       transcription TEXT,
       confidence REAL,
       created_at TIMESTAMP DEFAULT NOW()
   );
   ```

## 🚀 Usage

1. **Start the Flask server**
   ```bash
   python main.py
   ```

2. **Expose webhook with ngrok**
   ```bash
   ngrok http 5000
   ```

3. **Configure Green API webhook**
   - Set webhook URL to: `https://your-ngrok-url.ngrok.io/webhook`
   - Enable webhook notifications

4. **Access the web dashboard**
   - Open: `http://localhost:5000`
   - View tickets, send replies, upload files, record voice messages

## 📱 How It Works

### Message Flow
1. **Customer sends WhatsApp message** → Green API webhook → Flask server
2. **System creates/updates ticket** → Saves to Supabase database
3. **Agent responds via dashboard** → Sends via Green API → Customer receives

### Ticket Lifecycle
- **Open**: New tickets from customers
- **Active**: Tickets with agent responses
- **Closed**: Resolved tickets (can be reopened)

### Voice Message Processing
1. **Browser records audio** (WebM/OGG format)
2. **Server converts to MP3** (FFmpeg)
3. **Optimized for WhatsApp** (128kbps, mono, 44.1kHz)
4. **Sent via Green API** → Customer receives

## 🎯 Web Dashboard Features

### Ticket List
- View all tickets with status filtering
- Search by customer name or ticket ID
- Auto-refresh every 30 seconds

### Ticket Detail
- Complete message history
- Send text replies
- Upload files (drag & drop)
- Record voice messages
- Close/reopen tickets

### File Upload
- Support for images, videos, documents
- File size limit: 100MB
- Automatic file type detection
- Progress indicators

### Voice Recording
- Browser-based recording
- Audio preview before sending
- Automatic MP3 conversion
- WhatsApp-optimized format

## 🔧 Configuration

### Environment Variables
```bash
# Green API Configuration
GREEN_API_INSTANCE_ID=your_instance_id
GREEN_API_TOKEN_INSTANCE=your_token

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key

# Optional: Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
```

### Green API Setup
1. Create account at [Green API](https://green-api.com)
2. Get Instance ID and Token
3. Configure webhook URL
4. Enable required permissions

### Supabase Setup
1. Create project at [Supabase](https://supabase.com)
2. Run the provided SQL schema
3. Get URL and anon key from settings

## 📊 Database Schema

### Tickets Table
- `id`: Unique ticket identifier (T1, T2, etc.)
- `sender_id`: WhatsApp chat ID
- `sender_name`: Customer name
- `status`: open/closed
- `created_at`: Ticket creation timestamp
- `updated_at`: Last update timestamp

### Messages Table
- `ticket_id`: Reference to tickets table
- `author`: Message sender (customer name or 'Agent')
- `text`: Message content
- `message_type`: text/audio/image/video/document
- `file_url`: URL for media files
- `file_name`: Original filename
- `file_size`: File size in bytes
- `mime_type`: File MIME type
- `duration`: Audio/video duration
- `timestamp`: Message timestamp

## 🔍 Troubleshooting

### Common Issues

**Voice messages not working**
- Ensure FFmpeg is installed and in PATH
- Check browser microphone permissions
- Verify MP3 conversion in logs

**Webhook not receiving messages**
- Check ngrok URL is correct
- Verify Green API webhook configuration
- Ensure Flask server is running

**Database connection issues**
- Verify Supabase credentials
- Check network connectivity
- Review database schema

**File upload failures**
- Check file size limits
- Verify temporary directory permissions
- Review Green API file upload limits

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [Green API](https://green-api.com) for WhatsApp integration
- [Supabase](https://supabase.com) for database services
- [Bootstrap](https://getbootstrap.com) for UI components
- [FFmpeg](https://ffmpeg.org) for audio processing

## 📞 Support

For support and questions:
- Create an issue in this repository
- Check the troubleshooting section
- Review the logs for error details

---

**Built with ❤️ for efficient WhatsApp customer support**

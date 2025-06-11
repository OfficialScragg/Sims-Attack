import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Server Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    
    # SSL Configuration
    SSL_CERT = os.getenv('SSL_CERT', 'cert.pem')
    SSL_KEY = os.getenv('SSL_KEY', 'key.pem')
    USE_SSL = os.getenv('USE_SSL', 'False').lower() == 'true'
    
    # File Upload Configuration
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Database Configuration
    DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///c2.db')
    
    # Implant Configuration
    IMPLANT_CHECK_INTERVAL = int(os.getenv('IMPLANT_CHECK_INTERVAL', 30))  # seconds
    COMMAND_TIMEOUT = int(os.getenv('COMMAND_TIMEOUT', 300))  # seconds
    
    # Domain Spread Configuration
    DEFAULT_DOMAIN_USER = os.getenv('DEFAULT_DOMAIN_USER', '')
    DEFAULT_DOMAIN_PASSWORD = os.getenv('DEFAULT_DOMAIN_PASSWORD', '')
    
    # Create upload folder if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
import os
from datetime import time

class Config:
    """Configuration settings for AI Attendance System"""
    
    # Database Configuration
    DATABASE_PATH = 'database/attendance_system.db'
    
    # Directory Paths
    STUDENT_IMAGES_DIR = 'student_images'
    REPORTS_DIR = 'reports'
    TEMP_DIR = 'temp'
    LOGS_DIR = 'logs'
    BACKUP_DIR = 'backup'
    
    # Face Recognition Settings
    FACE_RECOGNITION_TOLERANCE = 0.6
    FACE_RECOGNITION_MODEL = 'hog'  # 'hog' or 'cnn'
    
    # Camera Settings
    CAMERA_INDEX = 0
    CAMERA_WIDTH = 640
    CAMERA_HEIGHT = 480
    CAMERA_FPS = 30
    
    # Image Processing
    FACE_DETECTION_SCALE = 0.25  # Scale down for faster processing
    MIN_FACE_SIZE = 50
    
    # Attendance Settings
    ATTENDANCE_TIMEOUT = 300  # Seconds between same person detections
    WORKING_HOURS_START = time(9, 0)  # 9:00 AM
    WORKING_HOURS_END = time(17, 0)   # 5:00 PM
    
    # Security Settings
    ADMIN_PASSWORD = "admin123"  # Change this in production
    
    # Report Settings
    REPORT_FORMATS = ['xlsx', 'csv', 'pdf']
    DEFAULT_REPORT_FORMAT = 'xlsx'
    
    # GUI Settings
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    THEME = 'default'
    
    # Email Settings (Optional)
    EMAIL_ENABLED = False
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    EMAIL_USERNAME = ''
    EMAIL_PASSWORD = ''
    
    # Logging Settings
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    LOG_ROTATION = True
    MAX_LOG_SIZE = 10485760  # 10MB
    
    # Backup Settings
    AUTO_BACKUP = True
    BACKUP_INTERVAL = 24  # Hours
    MAX_BACKUPS = 30
    
    # Recognition Settings
    RECOGNITION_THRESHOLD = 0.6
    MAX_FACES_PER_FRAME = 10
    
    # Performance Settings
    PROCESS_EVERY_N_FRAMES = 3  # Process every 3rd frame for better performance
    
    @classmethod
    def get_camera_settings(cls):
        """Get camera configuration"""
        return {
            'index': cls.CAMERA_INDEX,
            'width': cls.CAMERA_WIDTH,
            'height': cls.CAMERA_HEIGHT,
            'fps': cls.CAMERA_FPS
        }
    
    @classmethod
    def get_face_recognition_settings(cls):
        """Get face recognition configuration"""
        return {
            'tolerance': cls.FACE_RECOGNITION_TOLERANCE,
            'model': cls.FACE_RECOGNITION_MODEL,
            'threshold': cls.RECOGNITION_THRESHOLD
        }
    
    @classmethod
    def get_directory_paths(cls):
        """Get all directory paths"""
        return {
            'student_images': cls.STUDENT_IMAGES_DIR,
            'reports': cls.REPORTS_DIR,
            'temp': cls.TEMP_DIR,
            'logs': cls.LOGS_DIR,
            'backup': cls.BACKUP_DIR
        }
    
    @classmethod
    def ensure_directories(cls):
        """Create directories if they don't exist"""
        directories = cls.get_directory_paths()
        for directory in directories.values():
            os.makedirs(directory, exist_ok=True)
        
        # Also create database directory
        os.makedirs(os.path.dirname(cls.DATABASE_PATH), exist_ok=True)
    
    @classmethod
    def validate_config(cls):
        """Validate configuration settings"""
        errors = []
        
        # Check tolerance range
        if not 0.0 <= cls.FACE_RECOGNITION_TOLERANCE <= 1.0:
            errors.append("FACE_RECOGNITION_TOLERANCE must be between 0.0 and 1.0")
        
        # Check model type
        if cls.FACE_RECOGNITION_MODEL not in ['hog', 'cnn']:
            errors.append("FACE_RECOGNITION_MODEL must be 'hog' or 'cnn'")
        
        # Check camera settings
        if cls.CAMERA_INDEX < 0:
            errors.append("CAMERA_INDEX must be >= 0")
        
        if cls.CAMERA_WIDTH <= 0 or cls.CAMERA_HEIGHT <= 0:
            errors.append("Camera dimensions must be positive")
        
        # Check working hours
        if cls.WORKING_HOURS_START >= cls.WORKING_HOURS_END:
            errors.append("WORKING_HOURS_START must be before WORKING_HOURS_END")
        
        return errors
    
    @classmethod
    def load_from_file(cls, config_file='config.json'):
        """Load configuration from JSON file"""
        import json
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                # Update class attributes
                for key, value in config_data.items():
                    if hasattr(cls, key):
                        setattr(cls, key, value)
                
                return True
            except Exception as e:
                print(f"Error loading config file: {e}")
                return False
        
        return False
    
    @classmethod
    def save_to_file(cls, config_file='config.json'):
        """Save configuration to JSON file"""
        import json
        
        config_data = {}
        
        # Get all class attributes that are not methods
        for attr_name in dir(cls):
            if not attr_name.startswith('_') and not callable(getattr(cls, attr_name)):
                config_data[attr_name] = getattr(cls, attr_name)
        
        try:
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=4, default=str)
            return True
        except Exception as e:
            print(f"Error saving config file: {e}")
            return False

# Environment-specific configurations
class DevelopmentConfig(Config):
    """Development configuration"""
    LOG_LEVEL = 'DEBUG'
    AUTO_BACKUP = False
    FACE_RECOGNITION_MODEL = 'hog'  # Faster for development

class ProductionConfig(Config):
    """Production configuration"""
    LOG_LEVEL = 'INFO'
    AUTO_BACKUP = True
    FACE_RECOGNITION_MODEL = 'cnn'  # More accurate for production
    ADMIN_PASSWORD = "change_this_password"

class TestingConfig(Config):
    """Testing configuration"""
    DATABASE_PATH = 'test_attendance.db'
    LOG_LEVEL = 'DEBUG'
    AUTO_BACKUP = False
    ATTENDANCE_TIMEOUT = 10  # Shorter timeout for testing

# Configuration factory
def get_config(environment='development'):
    """Get configuration based on environment"""
    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig
    }
    
    return config_map.get(environment, DevelopmentConfig)
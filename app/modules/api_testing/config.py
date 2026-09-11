"""
Configuration file for K6 Load Testing Platform

Usage:
1. Copy to project root
2. Adjust values as needed
3. Set environment variables: export $(cat .env | xargs)
"""

# ============================================================================
# MongoDB Configuration
# ============================================================================

# Connection string for MongoDB
# Local development: mongodb://localhost:27017
# Docker Compose: mongodb://admin:mongodb123@mongodb:27017
# Atlas Cloud: mongodb+srv://username:password@cluster.mongodb.net/database
MONGO_URL = "mongodb://admin:mongodb123@localhost:27017"
MONGO_DB = "k6_testing"

# MongoDB username/password (if using authentication)
MONGO_USER = "admin"
MONGO_PASSWORD = "mongodb123"

# ============================================================================
# InfluxDB Configuration
# ============================================================================

# InfluxDB URL for K6 metrics storage
INFLUXDB_URL = "http://localhost:8086"
INFLUXDB_DB = "k6"
INFLUXDB_USER = ""  # Optional
INFLUXDB_PASSWORD = ""  # Optional

# ============================================================================
# FastAPI Configuration
# ============================================================================

API_HOST = "0.0.0.0"
API_PORT = 8000
API_RELOAD = True  # Auto-reload on code changes (development only)
API_LOG_LEVEL = "info"  # debug, info, warning, error, critical

# ============================================================================
# K6 Configuration
# ============================================================================

# Default K6 settings
K6_VUS = 10  # Virtual users
K6_DURATION = "60s"  # Test duration
K6_RAMP_UP = "30s"  # Ramp up duration

# K6 executable path
# If using Docker: "docker exec k6_runner k6"
# If installed locally: "k6"
K6_EXECUTABLE = "k6"

# K6 script working directory
K6_SCRIPTS_DIR = "/tmp"

# K6 timeout (seconds)
K6_TIMEOUT = 600

# ============================================================================
# Application Settings
# ============================================================================

# Max logs to return per request
MAX_LOGS = 200

# Max metrics to return per request
MAX_METRICS = 10000

# Enable detailed logging
DEBUG = False

# CORS origins (restrict in production)
ALLOWED_ORIGINS = ["*"]

# ============================================================================
# Email/Notifications (Optional)
# ============================================================================

# SMTP configuration for test completion notifications
SMTP_SERVER = ""
SMTP_PORT = 587
SMTP_USERNAME = ""
SMTP_PASSWORD = ""
NOTIFICATION_EMAIL = ""

# ============================================================================
# File Storage (Optional)
# ============================================================================

# Directory for temporary files
TEMP_DIR = "/tmp"

# Directory for logs/exports
LOGS_DIR = "./logs"

# Directory for reports
REPORTS_DIR = "./reports"
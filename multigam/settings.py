"""
Django settings for multigam project - Clean API Configuration
"""

import os
import json
from datetime import timedelta
from pathlib import Path
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ADD THESE DEBUG LINES RIGHT HERE:
print(f"🔍 DECOUPLE DEBUG: Current working directory: {os.getcwd()}")
print(f"🔍 DECOUPLE DEBUG: BASE_DIR: {BASE_DIR}")

# Also let's check if there are multiple .env files:
print(f"🔍 DECOUPLE DEBUG: Looking for .env files...")
for root, dirs, files in os.walk(BASE_DIR):
    for file in files:
        if file.startswith('.env'):
            env_path = os.path.join(root, file)
            print(f"🔍 Found .env file: {env_path}")


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='dev-secret-key-phase1')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
]

LOCAL_APPS = [
    'core',     # Base utilities
    'accounts',  # User management and authentication
    'reports',  # Reporting and analytics
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'multigam.urls'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False  # Important: must be False when using SSL/465
EMAIL_HOST_USER = 'askhntgaming@gmail.com'
EMAIL_HOST_PASSWORD = 'oziu vcug aszd twno'  # This must be an App Password
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


FRONTEND_BASE_URL = "https://report.hntgaming.me"

FRONTEND_URL = FRONTEND_BASE_URL

# Slack Webhook Configuration for Smart Alerts
SLACK_WEBHOOK_URL = config('SLACK_WEBHOOK_URL', default=None)
# Example: https://hooks.slack.com/services/YOUR/WEBHOOK/URL

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'multigam.wsgi.application'

# Database
# Use SQLite for local development, MySQL for production
if config('DEBUG', default=True, cast=bool):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'managed_inventory.db',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'  # Pakistan Standard Time (PKT)
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =====================================================================
# REST FRAMEWORK CONFIGURATION - CLEAN SEPARATION
# =====================================================================

REST_FRAMEWORK = {
    # Authentication: JWT-only for API, Session for admin interface
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    
    # Permissions: Require authentication by default
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    
    # Renderers: JSON for API, Browsable for development
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    
    # Pagination
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    
    # Exception handling
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# Add browsable API only in development
if DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'].append(
        'rest_framework.renderers.BrowsableAPIRenderer'
    )

# =====================================================================
# JWT CONFIGURATION
# =====================================================================

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    
    'JTI_CLAIM': 'jti',
}

# =====================================================================
# CORS CONFIGURATION
# =====================================================================

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="https://api.hntgaming.me,https://report.hntgaming.me,http://localhost:3010,http://127.0.0.1:3010"
).split(",")

# Set to True to allow all origins (for development only)
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=False, cast=bool)

CORS_ALLOW_CREDENTIALS = True

# CORS Headers
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]

# =====================================================================
# CSRF CONFIGURATION - PROPER SEPARATION
# =====================================================================

# CSRF for Django Admin (browser-based)
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://13.201.117.27',
    'https://13.201.117.27',
    'https://api.hntgaming.me',
]

# Keep CSRF enabled for admin interface
CSRF_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = True
CSRF_COOKIE_SAMESITE = 'Lax'

# =====================================================================
# DEVELOPMENT SETTINGS
# =====================================================================

if DEBUG:
    ALLOWED_HOSTS = ['*']
        
    # Logging for debugging
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            # gam_accounts logging removed
        },
    }

# =====================================================================
# GOOGLE AD MANAGER API CONFIGURATION (Updated for v202505)
# =====================================================================

# Helper function to load GAM credentials from JSON file
def load_gam_credentials():
    """Load GAM credentials from JSON file"""
    json_file_path = BASE_DIR / config('GAM_PRIVATE_KEY_FILE', default='key.json')
    
    if json_file_path.exists():
        try:
            with open(json_file_path, 'r') as f:
                credentials = json.load(f)
                return credentials
        except Exception as e:
            print(f"Error loading GAM credentials: {e}")
            return {}
    else:
        print(f"GAM credentials file not found at: {json_file_path}")
        return {}

# Load GAM credentials
_gam_credentials = load_gam_credentials()

# GAM Service Account Configuration
GAM_SERVICE_ACCOUNT_INFO = {
    'type': 'service_account',
    'project_id': config('GAM_PROJECT_ID', default='hnt-gaming'),
    'private_key_id': _gam_credentials.get('private_key_id', config('GAM_PRIVATE_KEY_ID', default='')),
    'private_key': _gam_credentials.get('private_key', config('GAM_PRIVATE_KEY', default='')).replace('\\n', '\n'),
    'client_email': config('GAM_CLIENT_EMAIL', default='report@hnt-gaming.iam.gserviceaccount.com'),
    'client_id': _gam_credentials.get('client_id', config('GAM_CLIENT_ID', default='')),
    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
    'token_uri': 'https://oauth2.googleapis.com/token',
    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
    'client_x509_cert_url': _gam_credentials.get('client_x509_cert_url', '')
}

# GAM API Configuration - CORRECTED SCOPES
GAM_CONFIG = {
    'PARENT_NETWORK_CODE': config('GAM_PARENT_NETWORK_CODE', default='152344380'),
    'CHILD_NETWORK_CODE': config('GAM_CHILD_NETWORK_CODE', default='22878573653'),
    'APPLICATION_NAME': config('GAM_APPLICATION_NAME', default='GAM Management Platform'),
    'API_VERSION': config('GAM_API_VERSION', default='v202508'),
    'SERVICE_ACCOUNT_INFO': GAM_SERVICE_ACCOUNT_INFO,
    # CRITICAL FIX: Use the correct scope for Ad Manager SOAP API
    'SCOPES': ['https://www.googleapis.com/auth/dfp'],  # This is correct for SOAP API
}

# Individual GAM settings for easy access
GAM_PARENT_NETWORK_CODE = GAM_CONFIG['PARENT_NETWORK_CODE']
GAM_CHILD_NETWORK_CODE = GAM_CONFIG['CHILD_NETWORK_CODE']
GAM_APPLICATION_NAME = GAM_CONFIG['APPLICATION_NAME']
GAM_API_VERSION = GAM_CONFIG['API_VERSION']

# CRITICAL: Add this missing field that your service account needs
GAM_SERVICE_ACCOUNT_EMAIL = GAM_SERVICE_ACCOUNT_INFO.get('client_email')

# Print GAM configuration in development
if DEBUG:
    print("🔧 GAM Configuration Loaded:")
    print(f"  - Parent Network: {GAM_PARENT_NETWORK_CODE}")
    print(f"  - Child Network: {GAM_CHILD_NETWORK_CODE} (FORCED TO PARENT FOR TESTING)")
    print(f"  - API Version: {GAM_API_VERSION}")
    print(f"  - Application: {GAM_APPLICATION_NAME}")
    print(f"  - Service Account: {GAM_SERVICE_ACCOUNT_INFO.get('client_email', 'Not loaded')}")
    print(f"  - Credentials File: {config('GAM_PRIVATE_KEY_FILE', 'Not specified')}")
    print(f"  - Private Key Loaded: {'Yes' if _gam_credentials.get('private_key') else 'No'}")
    print(f"  - Scope: {GAM_CONFIG['SCOPES'][0]}")

# Validation check
if not GAM_SERVICE_ACCOUNT_INFO.get('private_key'):
    print("⚠️  WARNING: GAM private key not loaded properly!")
    print("   Check your JSON credentials file and .env configuration")

if not GAM_SERVICE_ACCOUNT_INFO.get('client_email'):
    print("⚠️  WARNING: GAM service account email not found!")
    print("   Check your GAM_CLIENT_EMAIL in .env file")

print(f"🔍 CORS DEBUG:")
print(f"  - DEBUG: {DEBUG}")
print(f"  - CORS_ALLOWED_ORIGINS: {CORS_ALLOWED_ORIGINS}")
print(f"  - CORS_ALLOW_ALL_ORIGINS: {globals().get('CORS_ALLOW_ALL_ORIGINS', 'Not set')}")
print(f"  - ALLOWED_HOSTS: {ALLOWED_HOSTS}")
print(f"  - CORS_ALLOW_CREDENTIALS: {CORS_ALLOW_CREDENTIALS}")

# Additional verification
if 'CORS_ALLOW_ALL_ORIGINS' in globals() and CORS_ALLOW_ALL_ORIGINS:
    print("✅ CORS should accept ALL origins")
else:
    print("⚠️  CORS limited to specific origins only")


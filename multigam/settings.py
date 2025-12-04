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

# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY must be set in environment variables - no default for production
SECRET_KEY = config('SECRET_KEY', default=None)
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables for production")

# SECURITY WARNING: don't run with debug turned on in production!
# Force DEBUG to False for production (can be overridden via env var if needed)
DEBUG = config('DEBUG', default='False', cast=lambda v: v.lower() in ('true', '1', 'yes'))

# ALLOWED_HOSTS - explicitly list all allowed hosts (Django doesn't support wildcards)
# Get from environment variable or use default production hosts
allowed_hosts_str = config('ALLOWED_HOSTS', default='api2.hntgaming.me,api.hntgaming.me,localhost,127.0.0.1,publisher.hntgaming.me')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]

# Ensure api2.hntgaming.me is always included
if 'api2.hntgaming.me' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('api2.hntgaming.me')

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
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='notification@mail.hntgaming.me')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='fqho jbnd tedc dzhd')  # This must be an App Password
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)


FRONTEND_BASE_URL = "https://publisher.hntgaming.me"

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

# Database - PostgreSQL RDS (production-grade)
# Supports both PostgreSQL RDS and MySQL for flexibility
DB_ENGINE = config('DB_ENGINE', default='postgresql')

if DB_ENGINE.lower() == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {
                'connect_timeout': 10,
            },
        }
    }
else:
    # Fallback to MySQL if needed
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

# CORS allowed origins - get from env or use defaults
cors_origins_str = config(
    "CORS_ALLOWED_ORIGINS",
    default="https://publisher.hntgaming.me,https://api2.hntgaming.me,http://localhost:3010,http://127.0.0.1:3010"
)
# Clean and split origins
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

# Ensure publisher.hntgaming.me is always included
if 'https://publisher.hntgaming.me' not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append('https://publisher.hntgaming.me')

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
    'http://13.203.115.13',
    'https://13.203.115.13',
    'https://api.hntgaming.me',
]

# Keep CSRF enabled for admin interface
CSRF_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = True
CSRF_COOKIE_SAMESITE = 'Lax'

# =====================================================================
# DEVELOPMENT SETTINGS
# =====================================================================

# Security: Never allow all hosts, even in DEBUG mode
# if DEBUG:
#     ALLOWED_HOSTS = ['*']  # REMOVED - Security risk

if DEBUG:
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
            # Silent fail - credentials will be empty dict
            return {}
    else:
        return {}

# Load GAM credentials
_gam_credentials = load_gam_credentials()

# GAM Service Account Configuration
GAM_SERVICE_ACCOUNT_INFO = {
    'type': 'service_account',
    'project_id': config('GAM_PROJECT_ID', default='hnt-gaming'),
    'private_key_id': _gam_credentials.get('private_key_id', config('GAM_PRIVATE_KEY_ID', default='')),
    'private_key': _gam_credentials.get('private_key', config('GAM_PRIVATE_KEY', default='')).replace('\\n', '\n'),
    'client_email': config('GAM_CLIENT_EMAIL', default='ehumps@hnt-gaming.iam.gserviceaccount.com'),
    'client_id': _gam_credentials.get('client_id', config('GAM_CLIENT_ID', default='')),
    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
    'token_uri': 'https://oauth2.googleapis.com/token',
    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
    'client_x509_cert_url': _gam_credentials.get('client_x509_cert_url', '')
}

# GAM API Configuration - CORRECTED SCOPES
GAM_CONFIG = {
    'PARENT_NETWORK_CODE': config('GAM_PARENT_NETWORK_CODE', default='23310681755'),
    'CHILD_NETWORK_CODE': config('GAM_CHILD_NETWORK_CODE', default='23310681755'),
    'APPLICATION_NAME': config('GAM_APPLICATION_NAME', default='Managed Inventory Publisher Dashboard'),
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
# GAM configuration loaded - validation happens in services

# CORS configuration is complete - no debug output needed


import os
import warnings
import sys
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='http://localhost:8000,http://127.0.0.1:8000', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'crispy_forms',
    'crispy_tailwind',
    'corsheaders',
    'apps.accounts',
    'apps.posts',
    'apps.membership',
    'apps.payments',
    'apps.ai_engine',
    'apps.notifications',
    'apps.pages',
    'apps.recovery',
    'apps.messaging',
    'storages',
]

# Optional apps (safe to remove if dependencies not installed)
try:
    import django_celery_beat
    INSTALLED_APPS.append('django_celery_beat')
except ImportError:
    pass

if DEBUG:
    try:
        import debug_toolbar
        INSTALLED_APPS.append('debug_toolbar')
    except ImportError:
        pass

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.MembershipPendingMiddleware',
    'apps.accounts.middleware.MembershipMiddleware',
    'apps.accounts.middleware.ActiveUserMiddleware',
]

ROOT_URLCONF = 'core.urls'

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
                'apps.accounts.context_processors.site_settings',
                'apps.notifications.context_processors.unread_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='iubat_smartfind'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='postgres'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'core.storage.SupabasePublicStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MEDIA_URL = f'{config("SUPABASE_S3_ENDPOINT", default="https://localhost:8000")}/{config("SUPABASE_BUCKET", default="smartfind-media")}/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'pages:home'

CRISPY_ALLOWED_TEMPLATE_PACKS = 'tailwind'
CRISPY_TEMPLATE_PACK = 'tailwind'

# SSLCommerz
SSLCOMMERZ_STORE_ID = config('SSLCOMMERZ_STORE_ID', default='')
SSLCOMMERZ_STORE_PASS = config('SSLCOMMERZ_STORE_PASS', default='')
SSLCOMMERZ_IS_SANDBOX = config('SSLCOMMERZ_IS_SANDBOX', default=True, cast=bool)
SSLCOMMERZ_BASE_URL = 'https://sandbox.sslcommerz.com' if SSLCOMMERZ_IS_SANDBOX else 'https://secure.sslcommerz.com'

# Celery (optional)
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Dhaka'

# --- Jina AI Embeddings (API-based, no local model) ---
JINA_API_KEY = config('JINA_API_KEY', default='')
JINA_EMBEDDING_MODEL = config('JINA_EMBEDDING_MODEL', default='jina-embeddings-v5-text-nano')
JINA_API_BASE_URL = config('JINA_API_BASE_URL', default='https://api.jina.ai/v1/embeddings')
JINA_TIMEOUT = config('JINA_TIMEOUT', default=30, cast=int)
JINA_MAX_RETRIES = config('JINA_MAX_RETRIES', default=2, cast=int)
JINA_RATE_LIMIT_DELAY = config('JINA_RATE_LIMIT_DELAY', default=0.3, cast=float)
JINA_MAX_INPUT_CHARS = config('JINA_MAX_INPUT_CHARS', default=4000, cast=int)
# Output dimension for the embedding vectors (must match the pgvector column size)
JINA_EMBEDDING_DIMENSIONS = config('JINA_EMBEDDING_DIMENSIONS', default=256, cast=int)
AI_EMBEDDING_DIMENSIONS = JINA_EMBEDDING_DIMENSIONS

# --- AI Matching (hybrid scoring, weights sum to 1.0) ---
AI_MATCH_WEIGHTS = {
    'semantic': 0.60,
    'category': 0.15,
    'location': 0.10,
    'date': 0.10,
    'tags': 0.05,
}
AI_MATCH_THRESHOLD = config('AI_MATCH_THRESHOLD', default=0.35, cast=float)
AI_MATCH_CANDIDATES = config('AI_MATCH_CANDIDATES', default=20, cast=int)
AI_MATCH_RESULTS = config('AI_MATCH_RESULTS', default=5, cast=int)
AI_SEARCH_RESULTS = config('AI_SEARCH_RESULTS', default=20, cast=int)
AI_SEARCH_MIN_SCORE = config('AI_SEARCH_MIN_SCORE', default=0.25, cast=float)

# Site
SITE_NAME = config('SITE_NAME', default='IUBAT SmartFind')
SITE_URL = config('SITE_URL', default='http://localhost:8000')

# Email
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@iubat-smartfind.com')

# Supabase Storage (S3-compatible)
SUPABASE_BUCKET = config('SUPABASE_BUCKET', default='smartfind-media')

import storages.backends.s3boto3  # noqa - ensure storage backend is available

AWS_ACCESS_KEY_ID = config('SUPABASE_S3_ACCESS_KEY', default='')
AWS_SECRET_ACCESS_KEY = config('SUPABASE_S3_SECRET_KEY', default='')
AWS_STORAGE_BUCKET_NAME = SUPABASE_BUCKET
AWS_S3_ENDPOINT_URL = config('SUPABASE_S3_ENDPOINT', default='')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
AWS_DEFAULT_ACL = 'public-read'
AWS_QUERYSTRING_AUTH = False
AWS_S3_FILE_OVERWRITE = False
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

# Local settings override (for demo/dev - only in local env)
if os.environ.get('DJANGO_LOCAL', '').lower() in ('1', 'true', 'yes'):
    try:
        from local_settings import *  # noqa
    except ImportError:
        pass

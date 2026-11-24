import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local settings without overriding environment variables supplied by the host.
load_dotenv(BASE_DIR / '.env')


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name} must be a boolean value.')


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Project apps
    'apps.core',
    'apps.rooms',
    'apps.inquiries',
    'apps.reservations',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
# Default SQLite configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if DATABASE_URL:
    database_conn_max_age = 0 if os.getenv('VERCEL') == '1' else 600
    try:
        DATABASES['default'] = dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=database_conn_max_age,
            conn_health_checks=True,
            ssl_require=True,
        )
    except ValueError as exc:
        raise ImproperlyConfigured('DATABASE_URL is not a valid database URL.') from exc

USE_CLOUDINARY = _env_bool('USE_CLOUDINARY', default=False)
if USE_CLOUDINARY:
    cloudinary_credentials = {
        'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', '').strip(),
        'API_KEY': os.getenv('CLOUDINARY_API_KEY', '').strip(),
        'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', '').strip(),
    }
    missing_cloudinary_credentials = [
        key for key, value in cloudinary_credentials.items() if not value
    ]
    if missing_cloudinary_credentials:
        raise ImproperlyConfigured(
            'Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and '
            'CLOUDINARY_API_SECRET when USE_CLOUDINARY is enabled.'
        )

    INSTALLED_APPS += ['cloudinary_storage', 'cloudinary']
    CLOUDINARY_STORAGE = cloudinary_credentials
    STORAGES = {
        'default': {
            'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators
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
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (User uploaded content)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Protected media files (Sensitive uploads like payment proofs)
PROTECTED_MEDIA_ROOT = BASE_DIR / 'protected_media'

# Hotel business settings
DEFAULT_PAYMENT_DEADLINE_HOURS = int(os.getenv('DJANGO_PAYMENT_DEADLINE_HOURS', '24'))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'reservations@betedanielhotel.com')
LOGIN_URL = 'admin:login'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

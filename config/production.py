import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from .base import *

DEBUG = False

if not DATABASE_URL:
    raise ImproperlyConfigured(
        'DATABASE_URL must be set for production; SQLite is not supported on Vercel.'
    )

try:
    DATABASES['default'] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0,
        conn_health_checks=True,
        ssl_require=True,
    )
except ValueError as exc:
    raise ImproperlyConfigured('DATABASE_URL is not a valid database URL.') from exc

if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured(
        'Production DATABASE_URL must configure a PostgreSQL database.'
    )

# Production secret key sourced from environment variable
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

# Production allowed hosts (comma-separated list from environment variable)
_allowed_hosts = os.getenv('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts.split(',') if host.strip()]

# Security settings for production
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

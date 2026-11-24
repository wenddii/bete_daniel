import os
from .base import *

DEBUG = False

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

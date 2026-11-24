import os
from .base import *

DEBUG = True

SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-local-dev-key-bete-daniel-change-in-production'
)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1],testserver').split(',')
    if host.strip()
]

# Development email backend (console)
MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

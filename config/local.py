import os
from .base import *
from .base import _env_bool

DEBUG = _env_bool('DEBUG', default=True)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY') or (
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

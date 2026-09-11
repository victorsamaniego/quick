"""Fail closed before legacy maintenance scripts can import the application."""
import os
from urllib.parse import urlsplit


def require_local_maintenance(module_name):
    if module_name != '__main__':
        raise RuntimeError('Maintenance scripts must not be imported.')
    if os.environ.get('ALLOW_DESTRUCTIVE_MAINTENANCE') != 'YES':
        raise RuntimeError('Explicit ALLOW_DESTRUCTIVE_MAINTENANCE=YES is required.')
    if os.environ.get('FLASK_ENV', '').lower() == 'production' or os.environ.get('RAILWAY_ENVIRONMENT_ID'):
        raise RuntimeError('Production maintenance is disabled.')
    target = os.environ.get('MAINTENANCE_DATABASE_URL', '')
    try:
        parsed = urlsplit(target)
        local = parsed.scheme == 'sqlite' or (parsed.scheme in ('postgres', 'postgresql') and parsed.hostname in ('localhost', '127.0.0.1', '::1'))
    except ValueError:
        local = False
    if not local:
        raise RuntimeError('An explicit local MAINTENANCE_DATABASE_URL is required.')
    os.environ['DATABASE_URL'] = target

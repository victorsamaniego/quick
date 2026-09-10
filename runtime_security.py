"""Startup checks applied before any database or network extension initializes."""
import os
import secrets
from datetime import timedelta
from urllib.parse import urlsplit


def configure_runtime_security(app):
    environment = os.environ.get('FLASK_ENV', 'development').lower()
    database = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    production = environment == 'production' or (environment != 'testing' and
                                                str(database).startswith(('postgres:', 'postgresql:')))
    if production:
        if app.debug or app.testing or os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes'):
            raise RuntimeError('DEBUG/TESTING no están permitidos en producción.')
        key = app.secret_key
        if not isinstance(key, (str, bytes)) or len(key) < 32 or len(set(key)) < 12:
            raise RuntimeError('Producción requiere SECRET_KEY fuerte configurada explícitamente.')
    elif not app.secret_key:
        app.secret_key = secrets.token_bytes(32)
    app.config.update(SESSION_COOKIE_SECURE=production,
                      REMEMBER_COOKIE_SECURE=production,
                      REMEMBER_COOKIE_HTTPONLY=True,
                      REMEMBER_COOKIE_SAMESITE='Lax',
                      REMEMBER_COOKIE_DURATION=timedelta(days=7))
    app.config['SECURITY_PRODUCTION'] = production
    for flag in ('SECURITY_TOKEN_RECOVERY', 'SECURITY_SESSION_REVOCATION', 'SECURITY_DELIVERY_CANDIDATES'):
        app.config[flag] = os.environ.get(flag, '').lower() == 'true'
    for key in ('RESET_SMTP_HOST', 'RESET_SMTP_USERNAME', 'RESET_SMTP_PASSWORD', 'RESET_MAIL_FROM'):
        app.config[key] = os.environ.get(key, '')
    app.config['RESET_SMTP_PORT'] = int(os.environ.get('RESET_SMTP_PORT', '465'))
    app.config['SECURITY_ENFORCE_COVERAGE'] = os.environ.get('SECURITY_ENFORCE_COVERAGE', '').lower() == 'true'
    # Optional until the operator verifies every hostname used by staging/health checks.
    hosts = os.environ.get('TRUSTED_HOSTS', '')
    if hosts:
        app.config['TRUSTED_HOSTS'] = [host.strip() for host in hosts.split(',') if host.strip()]
    base = os.environ.get('PUBLIC_BASE_URL')
    if base:
        parsed = urlsplit(base)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
            raise RuntimeError('PUBLIC_BASE_URL debe ser un origen HTTPS explícito.')
        app.config['PUBLIC_BASE_URL'] = base.rstrip('/')
    if app.config['SECURITY_TOKEN_RECOVERY']:
        if not app.config['SECURITY_SESSION_REVOCATION']:
            raise RuntimeError('Recovery por tokens requiere revocación de sesiones activa.')
        if not base or not all(app.config[key] for key in ('RESET_SMTP_HOST', 'RESET_SMTP_USERNAME', 'RESET_SMTP_PASSWORD', 'RESET_MAIL_FROM')):
            raise RuntimeError('Recovery requiere PUBLIC_BASE_URL y configuración SMTP segura.')

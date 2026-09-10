"""Optional migrated password recovery. No schema creation or real mail at import."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import re
import secrets
import smtplib
import ssl
from threading import BoundedSemaphore, Lock
from urllib.parse import urlsplit
from flask import current_app
from models import db, User
from auth_identity import password_fingerprint
from security import rollback_on_error

GENERIC_RECOVERY_MESSAGE = 'Si la cuenta existe y está habilitada, recibirás instrucciones para recuperar el acceso.'
_dispatcher_lock = Lock()


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'
    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    password_fingerprint = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@rollback_on_error
def issue_reset_token(user_id):
    """User lock serializes issuance and consumption; return plaintext only in memory."""
    now = datetime.now(timezone.utc)
    user = User.query.filter_by(id=user_id).populate_existing().with_for_update().first()
    if not user or not user.is_active:
        db.session.rollback()
        return None
    last = PasswordResetToken.query.filter_by(user_id=user.id).order_by(PasswordResetToken.created_at.desc()).first()
    if last and (now - utc(last.created_at)).total_seconds() < 60:
        db.session.rollback()
        return None
    raw = secrets.token_urlsafe(32)
    PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update({'used_at': now})
    db.session.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        password_fingerprint=password_fingerprint(user), created_at=now, expires_at=now + timedelta(minutes=15)))
    db.session.commit()
    return raw


@rollback_on_error
def consume_reset_token(raw, password):
    if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', raw):
        return False
    if not isinstance(password, str) or len(password) > 1024 or User.validate_strong_password(password):
        return False
    digest = hashlib.sha256(raw.encode()).hexdigest()
    candidate = PasswordResetToken.query.filter_by(token_hash=digest).first()
    if not candidate:
        return False
    # Same locking order as issuance, regardless of which token was submitted.
    user = User.query.filter_by(id=candidate.user_id).populate_existing().with_for_update().first()
    token = PasswordResetToken.query.filter_by(id=candidate.id).populate_existing().with_for_update().first()
    now = datetime.now(timezone.utc)
    if (not user or not user.is_active or token.used_at is not None or utc(token.expires_at) <= now or
            not hmac.compare_digest(token.password_fingerprint, password_fingerprint(user))):
        db.session.rollback()
        return False
    try:
        claimed = PasswordResetToken.query.filter_by(id=token.id, used_at=None).update(
            {'used_at': now}, synchronize_session=False)
        if claimed != 1:
            db.session.rollback()
            return False
        user.set_password(password)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True


def reset_link(raw):
    base = current_app.config.get('PUBLIC_BASE_URL', '')
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise RuntimeError('PUBLIC_BASE_URL HTTPS es obligatorio para recovery.')
    # Fragments are not sent in HTTP requests/access logs or Referer.
    return base.rstrip('/') + '/recover/token#' + raw


def smtp_send(recipient, link):
    config = current_app.config
    message = EmailMessage()
    message['From'] = config['RESET_MAIL_FROM']
    message['To'] = recipient
    message['Subject'] = 'Recuperación de acceso a QuickGo'
    message.set_content('Para elegir una nueva contraseña, abrí este enlace. Expira en 15 minutos y se usa una sola vez.\n\n'
                        + link + '\n\nSi no lo solicitaste, podés ignorar este correo.')
    port = config.get('RESET_SMTP_PORT', 465)
    if port == 465:
        connection = smtplib.SMTP_SSL(config['RESET_SMTP_HOST'], port, timeout=10, context=ssl.create_default_context())
    else:
        connection = smtplib.SMTP(config['RESET_SMTP_HOST'], port, timeout=10)
    with connection as client:
        if port != 465:
            client.starttls(context=ssl.create_default_context())
        client.login(config['RESET_SMTP_USERNAME'], config['RESET_SMTP_PASSWORD'])
        client.send_message(message)


def schedule_recovery(identifier):
    """Queue identical work for known/unknown identifiers. Bounded, best-effort mail delivery."""
    app = current_app._get_current_object()
    def work():
        with app.app_context():
            try:
                user = User.query.filter((User.email == identifier) | (User.username == identifier)).first()
                if not user or not user.is_active:
                    return
                recipient, user_id = user.email, user.id
                raw = issue_reset_token(user_id)
                if raw:
                    app.config.get('RESET_MAIL_SENDER', smtp_send)(recipient, reset_link(raw))
            except Exception:
                db.session.rollback()
                app.logger.warning('Password recovery could not be delivered')
            finally:
                db.session.remove()
    # In-process adapter is injectable for isolated tests, never supplied by HTTP input.
    dispatch = app.config.get('RESET_MAIL_DISPATCH')
    if dispatch:
        dispatch(work)
        return
    with _dispatcher_lock:
        state = app.extensions.get('password_recovery_dispatch')
        if state is None:
            state = (ThreadPoolExecutor(max_workers=2, thread_name_prefix='recovery'), BoundedSemaphore(64))
            app.extensions['password_recovery_dispatch'] = state
    executor, slots = state
    if not slots.acquire(blocking=False):
        app.logger.warning('Password recovery queue is full')
        return
    try:
        executor.submit(work).add_done_callback(lambda _: slots.release())
    except Exception:
        slots.release()
        app.logger.warning('Password recovery queue unavailable')

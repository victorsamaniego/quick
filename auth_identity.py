"""Flask-Login alternative ids tied to the current salted password hash."""
import hashlib
import hmac
import re
from flask import current_app


def password_fingerprint(user):
    key = current_app.secret_key
    key = key.encode() if isinstance(key, str) else key
    return hmac.new(key, f'{user.id}:{user.password_hash}'.encode(), hashlib.sha256).hexdigest()


def authentication_id(user):
    if not current_app.config.get('SECURITY_SESSION_REVOCATION', False):
        return str(user.id)
    return f'v1.{user.id}.{password_fingerprint(user)}'


def matches_identity(user, identity):
    return bool(user and user.is_active and isinstance(identity, str) and
                hmac.compare_digest(authentication_id(user), identity))


def load_security_user(identity):
    from models import db, User
    if not isinstance(identity, str) or len(identity) > 100:
        return None
    revocation = current_app.config.get('SECURITY_SESSION_REVOCATION', False)
    pattern = r'v1\.([1-9][0-9]{0,18})\.[0-9a-f]{64}' if revocation else r'([1-9][0-9]{0,18})'
    match = re.fullmatch(pattern, identity)
    if not match:
        return None
    if int(match[1]) > 9223372036854775807:
        return None
    user = db.session.get(User, int(match[1]), populate_existing=True)
    return user if matches_identity(user, identity) else None

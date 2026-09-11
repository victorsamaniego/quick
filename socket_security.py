"""Per-account event budgets for the current single-worker deployment."""
from functools import wraps
from threading import Lock
from time import monotonic
from flask import current_app
from flask_login import current_user


def socket_budget(event, limit):
    def decorate(view):
        @wraps(view)
        def guarded(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_active:
                return {'success': False}
            state = current_app.extensions.setdefault('socket_budgets', {'lock': Lock(), 'entries': {}})
            now = monotonic()
            key = (current_user.id, event)
            with state['lock']:
                entries = state['entries']
                start, count = entries.get(key, (now, 0))
                if now - start >= 60:
                    start, count = now, 0
                if key not in entries and len(entries) >= 10000:
                    expired = [k for k, (at, _) in entries.items() if now - at >= 60]
                    for expired_key in expired:
                        del entries[expired_key]
                    if len(entries) >= 10000:
                        return {'success': False}
                if count >= limit:
                    return {'success': False, 'error': 'rate limit'}
                entries[key] = (start, count + 1)
            return view(*args, **kwargs)
        return guarded
    return decorate

"""Opt-in Web Push. Private room audiences remain the source of authorization."""
import base64
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import BoundedSemaphore
from urllib.parse import urlsplit
from requests import Session

from flask import current_app
from models import db, User


class PushSubscription(db.Model):
    __tablename__ = 'web_push_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    endpoint_hash = db.Column(db.String(64), unique=True, nullable=False)
    endpoint = db.Column(db.String(2048), nullable=False)
    p256dh = db.Column(db.String(128), nullable=False)
    auth = db.Column(db.String(32), nullable=False)
    visible_at = db.Column(db.DateTime(timezone=True))


def enabled():
    config = current_app.config
    return bool(config.get('WEB_PUSH_ENABLED', False) and all(config.get(key) for key in (
        'WEB_PUSH_VAPID_PUBLIC_KEY', 'WEB_PUSH_VAPID_PRIVATE_KEY', 'WEB_PUSH_CONTACT')))


def endpoint_hash(endpoint):
    return hashlib.sha256(endpoint.encode()).hexdigest()


def valid_endpoint(endpoint):
    if not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 2048 or any(ord(c) < 33 for c in endpoint):
        return False
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ''
        # Do not turn user-supplied subscriptions into a server-side URL fetcher.
        trusted = host in {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'} or host.endswith('.push.apple.com') or host.endswith('.notify.windows.com')
        return bool(trusted and url.scheme == 'https' and url.port in (None, 443) and not url.username and not url.password and not url.fragment and url.path.startswith('/'))
    except ValueError:
        return False


def valid_key(value, size):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}={0,2}', value):
        return False
    try:
        decoded = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        return len(decoded) == size and (size != 65 or decoded[0] == 4)
    except ValueError:
        return False


def validate_subscription(data):
    if not isinstance(data, dict) or set(data) - {'endpoint', 'keys', 'expirationTime'}:
        return False
    keys = data.get('keys')
    return (valid_endpoint(data.get('endpoint')) and isinstance(keys, dict) and set(keys) == {'p256dh', 'auth'}
            and valid_key(keys.get('p256dh'), 65) and valid_key(keys.get('auth'), 16))


EVENTS = {'new_order': 'Nuevo pedido', 'new_chat_message': 'Nuevo mensaje',
          'private_chat_message': 'Nuevo mensaje', 'new_delivery_request': 'Solicitud de delivery',
          'delivery_assigned': 'Delivery asignado', 'order_status_update': 'Pedido actualizado',
          'superadmin_notification': 'Nuevo aviso de QuickGo'}


def push_payload(event, payload, user):
    from flask import url_for
    order_id = payload.get('order_id')
    url = url_for('main.dashboard')
    if event == 'new_order':
        url = url_for('admin.manage_orders')
    elif event == 'new_delivery_request':
        url = url_for('main.delivery_requests_list')
    elif event == 'new_chat_message':
        url = url_for('main.order_chat', order_id=order_id)
    elif event == 'private_chat_message':
        channel = payload.get('channel', '')
        if channel.startswith('delivery_chat_'):
            url = url_for('main.chat_delivery_negocio', order_id=int(channel.split('_')[-1]))
        elif channel.startswith('support_'):
            url = url_for('super_admin.soporte_admin', business_id=int(channel.split('_')[-1])) if user.is_super_admin else url_for('main.soporte')
    elif event == 'superadmin_notification':
        url = '/notificacion/' + str(payload['notification_id'])
    elif order_id:
        url = url_for('main.order_tracking', order_id=order_id)
    title = EVENTS[event]
    if event == 'order_status_update':
        title = {'shipped': 'Tu pedido está en camino', 'delivered': 'Pedido entregado', 'picked_up': 'Pedido retirado', 'cancelled': 'Pedido cancelado'}.get(payload.get('status'), title)
    identity = payload.get('event_id') or f"{event}:{payload.get('channel', '')}:{payload.get('notification_id') or payload.get('request_id') or payload.get('message', {}).get('id') or order_id}"
    # No customer address, GPS or message text on a locked/shared device.
    return {'event_id': str(identity), 'title': title, 'body': (f'Tu pedido #{order_id} fue registrado como retirado del local.' if event == 'order_status_update' and payload.get('status') == 'picked_up' else 'Abrí QuickGo para ver los detalles.'), 'url': url, 'user_id': user.id}


class PushHTTPSession(Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def send_to_subscription(row, payload):
    from pywebpush import webpush, WebPushException
    try:
        if not valid_endpoint(row.endpoint):
            return
        with PushHTTPSession() as transport:
            webpush(subscription_info={'endpoint': row.endpoint, 'keys': {'p256dh': row.p256dh, 'auth': row.auth}},
                    data=json.dumps(payload), vapid_private_key=current_app.config['WEB_PUSH_VAPID_PRIVATE_KEY'],
                    vapid_claims={'sub': current_app.config['WEB_PUSH_CONTACT']}, ttl=60, timeout=5,
                    requests_session=transport)
    except WebPushException as error:
        if error.response is not None and error.response.status_code in (404, 410):
            db.session.delete(row)
            db.session.commit()
        else:
            current_app.logger.warning('Web Push delivery failed (provider response omitted).')
    except Exception:
        # Provider errors can contain endpoint capabilities/keys: never log them.
        current_app.logger.warning('Web Push delivery failed (details omitted).')


def deliver(event, payload, rooms):
    from realtime import allowed_room
    now = datetime.now(timezone.utc)
    sender = payload.get('message', {}).get('sender_id')
    # Query only subscribed users; revalidate room access at actual send time.
    for row in PushSubscription.query.all():
        user = db.session.get(User, row.user_id, populate_existing=True)
        if not user or user.id == sender or not any(allowed_room(user, room) for room in rooms):
            continue
        if row.visible_at and (now - row.visible_at.replace(tzinfo=timezone.utc)).total_seconds() < 40:
            continue
        send_to_subscription(row, push_payload(event, payload, user))


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='quickgo-push')
_slots = BoundedSemaphore(100)


def enqueue(event, payload, rooms):
    if event not in EVENTS or not enabled():
        return
    if not _slots.acquire(blocking=False):
        current_app.logger.warning('Web Push queue full; durable inbox remains available.')
        return
    app = current_app._get_current_object()
    # Detached JSON copy: no request context or live ORM entities cross threads.
    payload = json.loads(json.dumps(payload))
    def run():
        try:
            with app.test_request_context('/'):
                try:
                    deliver(event, payload, rooms)
                except Exception:
                    db.session.rollback()
                    app.logger.warning('Web Push unavailable; notification remains in QuickGo.')
        finally:
            _slots.release()
    try:
        _executor.submit(run)
    except Exception:
        _slots.release()
        app.logger.warning('Web Push worker unavailable.')

"""Shared transport and server-side audiences. Importing this never creates an app."""
import re
from socket_security import socket_budget
import time
from uuid import uuid4
from flask import current_app, request, session
from auth_identity import matches_identity
from flask_login import current_user
from flask_socketio import SocketIO, join_room, leave_room
from models import db, User, Order

socketio = SocketIO()


def can_access_order(user, order):
    return bool(user and user.is_authenticated and order and (
        user.id == order.user_id or
        (user.is_delivery and user.id == order.delivery_driver_id) or
        (user.is_admin and user.business_id == order.business_id)))


def allowed_room(user, room):
    if not user or not user.is_authenticated or not user.is_active or not isinstance(room, str) or len(room) > 96:
        return False
    if room == 'admin':
        return bool(user.is_super_admin)
    match = re.fullmatch(r'(user|delivery|business|order|order_chat|support|delivery_chat)_(\d+)', room)
    if not match:
        return False
    kind, ident = match[1], int(match[2])
    if kind == 'user':
        return user.id == ident
    if kind == 'delivery':
        return user.is_delivery and user.id == ident
    if kind == 'business':
        return user.is_admin and user.business_id == ident
    if kind == 'support':
        return user.is_super_admin or (user.is_admin and user.business_id == ident)
    order = db.session.get(Order, ident)
    if kind == 'delivery_chat':
        return bool(order and ((user.is_delivery and user.id == order.delivery_driver_id) or
                              (user.is_admin and user.business_id == order.business_id)))
    return can_access_order(user, order)


def canonical_room(room):
    return room.replace('order_chat_', 'order_', 1) if isinstance(room, str) else room


def publish(event, payload, rooms):
    """Recheck membership before emission, including assignments revoked since join.

    Socket.IO's room union delivers once to a socket present in several rooms.
    """
    if 'socketio' not in current_app.extensions:
        return
    identities = current_app.extensions.get('realtime_identities', {})
    for room in rooms:
        for sid, _ in list(socketio.server.manager.get_participants('/', room)):
            user = db.session.get(User, identities.get(sid), populate_existing=True) if sid in identities else None
            revoked = current_app.config.get('SECURITY_SESSION_REVOCATION', False) and not matches_identity(
                user, current_app.extensions.get('realtime_auth_ids', {}).get(sid))
            if revoked or not allowed_room(user, room):
                socketio.server.leave_room(sid, room, namespace='/')
    try:
        socketio.emit(event, {**payload, 'emitted_at': time.time()}, to=rooms)
    except Exception:
        current_app.logger.exception('Realtime emission failed after persistence: %s', event)


def order_rooms(order):
    rooms = [f'order_{order.id}', f'user_{order.user_id}', f'business_{order.business_id}']
    if order.delivery_driver_id:
        rooms.append(f'delivery_{order.delivery_driver_id}')
    return rooms


def publish_status(order, old_status):
    if old_status == order.status:
        return
    publish('order_status_update', {
        'event_id': uuid4().hex, 'order_id': order.id, 'user_id': order.user_id,
        'business_id': order.business_id, 'status': order.status,
        'new_status': order.status, 'old_status': old_status,
        'delivery_driver_id': order.delivery_driver_id, 'status_label': order.status_label,
        'status_color': order.status_color,
    }, order_rooms(order))


def register_realtime(app):
    app.extensions['realtime_identities'] = {}
    app.extensions['realtime_auth_ids'] = {}

    @socketio.on('connect')
    def connect(auth=None):
        if not current_user.is_authenticated or not current_user.is_active:
            return False
        socketio.emit('realtime_ready', {'live_since': time.time()}, to=request.sid)
        app.extensions['realtime_identities'][request.sid] = current_user.id
        app.extensions['realtime_auth_ids'][request.sid] = session.get('_user_id')
        join_room(f'user_{current_user.id}')
        if current_user.is_admin and current_user.business_id:
            join_room(f'business_{current_user.business_id}')
        if current_user.is_delivery:
            join_room(f'delivery_{current_user.id}')
        if current_user.is_super_admin:
            join_room('admin')

    @socketio.on('disconnect')
    def disconnect(reason=None):
        app.extensions['realtime_identities'].pop(request.sid, None)
        app.extensions['realtime_auth_ids'].pop(request.sid, None)

    @socket_budget('join', 120)
    def join(data=None):
        data = data if isinstance(data, dict) else {}
        room = canonical_room(data.get('room'))
        if not allowed_room(current_user, room):
            return {'success': False}
        join_room(room)
        return {'success': True, 'room': room}

    def field(data, key):
        return data.get(key) if isinstance(data, dict) else None

    socketio.on_event('join', join)
    socketio.on_event('join_order_room', lambda data=None: join({
        'room': f"order_{field(data, 'order_id')}"}))
    socketio.on_event('join_business_room', lambda data=None: join({
        'room': f"business_{field(data, 'business_id')}"}))
    socketio.on_event('join_user_room', lambda data=None: join({
        'room': f"user_{field(data, 'user_id')}"}))
    socketio.on_event('join_delivery_room', lambda data=None: join({
        'room': f"delivery_{field(data, 'user_id')}"}))
    socketio.on_event('join_admin_room', lambda data=None: join({'room': 'admin'}))

    @socketio.on('leave')
    @socket_budget('leave', 120)
    def leave(data=None):
        room = canonical_room(data.get('room')) if isinstance(data, dict) else None
        if allowed_room(current_user, room):
            leave_room(room)

    @socketio.on('request_order_update')
    @socket_budget('snapshot', 120)
    def snapshot(data=None):
        ident = data.get('order_id') if isinstance(data, dict) else None
        if not isinstance(ident, int):
            return {'success': False}
        order = db.session.get(Order, ident)
        if not can_access_order(current_user, order):
            return {'success': False}
        return {'success': True, 'order_id': order.id, 'status': order.status,
                'status_label': order.status_label, 'status_color': order.status_color}

    @socketio.on('user_location_update')
    @socket_budget('location', 240)
    def user_location(data):
        if current_user.is_authenticated and isinstance(data, dict) and data.get('user_id') == current_user.id:
            try:
                lat, lon = float(data['latitude']), float(data['longitude'])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    return
            except (KeyError, TypeError, ValueError):
                return
            publish('client_location_update', {'user_id': current_user.id,
                    'latitude': lat, 'longitude': lon}, ['admin'])

    @socketio.on('delivery_location_update')
    @socket_budget('location', 240)
    def delivery_location(data):
        if not isinstance(data, dict) or not isinstance(data.get('order_id'), int):
            return
        order = db.session.get(Order, data['order_id'])
        if order and current_user.is_authenticated and current_user.is_delivery and order.delivery_driver_id == current_user.id:
            try:
                lat, lon = float(data['latitude']), float(data['longitude'])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    return
            except (KeyError, TypeError, ValueError):
                return
            publish('delivery_location_update', {'order_id': order.id, 'latitude': lat,
                                                 'longitude': lon}, order_rooms(order))

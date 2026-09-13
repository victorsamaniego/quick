"""Audience segmentation on the existing notification and recipient tables."""
from itertools import combinations
from flask import abort
from models import db, User, Notification, NotificationRecipient

AUDIENCES = {'customer': 'Compradores', 'business': 'Comercios', 'delivery': 'Delivery'}


def user_audience(user):
    if not user or not user.is_authenticated or not user.is_active or user.is_super_admin:
        return None
    # Match the panel routing order; a driver who also has is_admin uses delivery.
    if user.is_delivery:
        return 'delivery'
    if user.is_admin:
        return 'business' if user.business_id else None
    return 'customer'


def decode_audiences(value):
    if value == 'all':
        return set(AUDIENCES)
    return set((value or '').split(',')) & set(AUDIENCES)


def audience_label(value):
    selected = decode_audiences(value)
    return ' · '.join(label for key, label in AUDIENCES.items() if key in selected)


def parse_audiences(form):
    if 'audiences' in form and 'notification_type' in form:
        abort(400, description='Elegí un único formato de destinatarios.')
    if 'audiences' in form:
        values = form.getlist('audiences')
    else:
        values = form.getlist('notification_type')
        if values == ['all']:
            values = list(AUDIENCES)
    if not values or len(values) != len(set(values)) or not set(values) <= set(AUDIENCES):
        abort(400, description='Seleccioná al menos una audiencia válida.')
    return set(values)


def recipient_query(user):
    audience = user_audience(user)
    # Canonical combinations fit in the existing String(50), retaining legacy values.
    types = ['all'] + [','.join(group) for size in range(1, 4)
                       for group in combinations(sorted(AUDIENCES), size) if audience in group]
    return NotificationRecipient.query.join(Notification).filter(
        NotificationRecipient.user_id == user.id,
        Notification.is_sent.is_(True),
        Notification.notification_type.in_(types) if audience else db.false())


def payload(notification, audience):
    return dict(notification_id=notification.id, title=notification.title,
                message=notification.message, audience=audience,
                created_at=notification.created_at.isoformat() if notification.created_at else None)


def create_broadcast(form, sender):
    if not sender.is_super_admin:
        abort(403)
    if set(form) - {'csrf_token', 'title', 'message', 'audiences', 'notification_type'}:
        abort(400, description='Formulario inválido.')
    if any(len(form.getlist(key)) > 1 for key in ('title', 'message', 'notification_type')):
        abort(400, description='Formulario inválido.')
    title, message = form.get('title', '').strip(), form.get('message', '').strip()
    if not 1 <= len(title) <= 200 or not 1 <= len(message) <= 2000:
        abort(400, description='Título (1–200) y mensaje (1–2000) son obligatorios.')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in title + message):
        abort(400, description='El contenido incluye caracteres de control inválidos.')
    selected = parse_audiences(form)
    notification = Notification(title=title, message=message,
                                notification_type=','.join(sorted(selected)), sent_by=sender.id)
    users = [user for user in User.query.filter_by(is_active=True).all() if user_audience(user) in selected]
    db.session.add(notification)
    db.session.flush()
    db.session.add_all([NotificationRecipient(notification_id=notification.id, user_id=user.id) for user in users])
    notification.is_sent = True
    db.session.commit()
    # Persist first. Send to existing private user rooms, never a global broadcast.
    from realtime import publish
    for user in users:
        audience = user_audience(user)
        if audience in selected:
            publish('superadmin_notification', payload(notification, audience), [f'user_{user.id}'])
    return notification, len(users)

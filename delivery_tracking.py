"""One last GPS sample per order, never a route history or user location."""
from datetime import datetime, timezone
from math import isfinite
from models import db, Order


class DeliveryLocation(db.Model):
    __tablename__ = 'order_delivery_locations'
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)


def point(lat, lon):
    if type(lat) not in (int, float) or type(lon) not in (int, float):
        return None
    if not isfinite(lat) or not isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
        return None
    return {'latitude': lat, 'longitude': lon}


def tracking_snapshot(order, user):
    row = db.session.get(DeliveryLocation, order.id)
    position = None
    if row and row.driver_id == order.delivery_driver_id:
        at = row.updated_at.replace(tzinfo=timezone.utc)
        position = {**point(row.latitude, row.longitude), 'accuracy': row.accuracy,
                    'updated_at': at.timestamp()}
    return {'success': True, 'order_id': order.id, 'status': order.status,
            'active': order.tracking_active, 'delivery_driver_id': order.delivery_driver_id,
            'can_transmit': bool(order.tracking_active and user.is_delivery and user.id == order.delivery_driver_id),
            'pickup': point(order.business.latitude, order.business.longitude) if order.business else None,
            'dropoff': point(order.client_latitude, order.client_longitude), 'position': position,
            'stale': bool(position and datetime.now(timezone.utc).timestamp() - position['updated_at'] > 25)}


def save_location(data, user):
    if not isinstance(data, dict) or set(data) != {'order_id', 'latitude', 'longitude', 'accuracy'}:
        return {'success': False}
    ident, accuracy = data['order_id'], data['accuracy']
    if type(ident) is not int or not 0 < ident <= 2147483647:
        return {'success': False}
    coords = point(data['latitude'], data['longitude'])
    if not coords or type(accuracy) not in (int, float) or not isfinite(accuracy) or not 0 <= accuracy <= 100000:
        return {'success': False}
    if not user.is_authenticated or not user.is_active or not user.is_delivery:
        return {'success': False}
    try:
        # Serialize with assignment and completion writers. Recheck fresh DB state.
        order = Order.query.filter_by(id=ident).populate_existing().with_for_update().first()
        if not order or not order.tracking_active or order.delivery_driver_id != user.id:
            db.session.rollback()
            return {'success': False, 'error': 'inactive'}
        now = datetime.now(timezone.utc)
        row = db.session.get(DeliveryLocation, ident)
        if row and row.driver_id == user.id and (now - row.updated_at.replace(tzinfo=timezone.utc)).total_seconds() < 5:
            db.session.rollback()
            return {'success': False, 'error': 'throttled'}
        if row is None:
            row = DeliveryLocation(order_id=ident)
            db.session.add(row)
        row.driver_id, row.latitude, row.longitude = user.id, coords['latitude'], coords['longitude']
        row.accuracy, row.updated_at = accuracy, now
        db.session.commit()
        from realtime import publish, order_rooms
        payload = {'order_id': ident, **coords, 'accuracy': accuracy, 'updated_at': now.timestamp(),
                   'delivery_driver_id': user.id}
        publish('delivery_location_update', payload, order_rooms(order))
        return {'success': True, **payload}
    except Exception:
        db.session.rollback()
        raise

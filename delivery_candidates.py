"""Opt-in dispatch: persist recipients, serialize on the order, commit before events."""
from datetime import datetime, timedelta, timezone
from math import isfinite

from flask import abort
from sqlalchemy import text
from models import db, User, Order, DeliveryRequest
from security import rollback_on_error


class DeliveryRequestCandidate(db.Model):
    __tablename__ = 'delivery_request_candidates'
    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True)
    delivery_request_id = db.Column(db.Integer, db.ForeignKey('delivery_requests.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    approximate_distance_km = db.Column(db.Integer, nullable=False)
    notified_at = db.Column(db.DateTime(timezone=True), nullable=False)
    responded_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.UniqueConstraint('delivery_request_id', 'driver_id'),
        db.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'expired', 'cancelled')"),
        db.CheckConstraint('approximate_distance_km >= 0'),
        db.Index('uq_delivery_candidate_one_winner', 'delivery_request_id', unique=True,
                 postgresql_where=text("status = 'accepted'"), sqlite_where=text("status = 'accepted'")),
    )


def candidates(request_id):
    return DeliveryRequestCandidate.query.filter_by(delivery_request_id=request_id)


def close_pending(request_id, status, now):
    candidates(request_id).filter_by(status='pending').update(
        {'status': status, 'responded_at': now}, synchronize_session='fetch')


@rollback_on_error
def create_dispatch(order_id, business_id, radius):
    order = Order.query.filter_by(id=order_id).populate_existing().with_for_update().first_or_404()
    if order.business_id != business_id:
        abort(403)
    if order.status != 'pending' or order.delivery_driver_id is not None:
        abort(409)
    from routes import validar_coordenadas
    try:
        lat, lon = validar_coordenadas(order.client_latitude, order.client_longitude)
    except (ValueError, TypeError):
        abort(400)
    now = datetime.now(timezone.utc)
    previous = DeliveryRequest.query.filter_by(order_id=order_id, status='pending').order_by(
        DeliveryRequest.id).populate_existing().with_for_update().all()
    for req in previous:
        if not req.is_expired():
            if not candidates(req.id).first():
                # Never invent historical recipients when enabling this feature.
                abort(409, description='Espere a que expire la solicitud anterior.')
            rows = candidates(req.id).all()
            db.session.commit()
            return req, rows, False
        req.status = 'expired'
        close_pending(req.id, 'expired', now)
    recipients = {}
    for item in User.find_nearby_deliveries(lat, lon, radius, business_id=None):
        driver, distance = item['delivery'], float(item['distance'])
        if driver.is_delivery and driver.is_active and isfinite(distance) and 0 <= distance <= radius:
            recipients[driver.id] = round(distance)
    if not recipients:
        db.session.commit()
        return None, [], False
    req = DeliveryRequest(order_id=order_id, business_id=business_id, search_radius=radius,
                          expires_at=now + timedelta(minutes=2), status='pending')
    db.session.add(req); db.session.flush()
    rows = [DeliveryRequestCandidate(delivery_request_id=req.id, driver_id=driver_id,
            approximate_distance_km=distance, notified_at=now) for driver_id, distance in sorted(recipients.items())]
    db.session.add_all(rows); db.session.commit()
    return req, rows, True


@rollback_on_error
def respond(request_id, user, accept):
    if not user.is_active or not user.is_delivery:
        abort(403)
    reference = db.session.get(DeliveryRequest, request_id)
    if reference is None:
        abort(404)
    # All dispatch writers use order -> request -> candidate, including retries.
    order = Order.query.filter_by(id=reference.order_id).populate_existing().with_for_update().first_or_404()
    req = DeliveryRequest.query.filter_by(id=request_id).populate_existing().with_for_update().first_or_404()
    candidate = candidates(request_id).filter_by(driver_id=user.id).populate_existing().with_for_update().first()
    if candidate is None:
        abort(403)
    if accept and candidate.status == 'accepted' and req.driver_id == user.id and order.delivery_driver_id == user.id:
        db.session.commit()
        return req, order, False
    if not accept and candidate.status == 'rejected':
        db.session.commit()
        return req, order, False
    if candidate.status != 'pending' or req.status != 'pending' or req.is_expired() or order.status != 'pending' or order.delivery_driver_id is not None:
        abort(409)
    now = datetime.now(timezone.utc)
    if accept:
        won = Order.query.filter_by(id=order.id, status='pending', delivery_driver_id=None).update(
            {'delivery_driver_id': user.id, 'status': 'shipped'}, synchronize_session='fetch')
        if won != 1:
            abort(409)
        candidate.status = 'accepted'; candidate.responded_at = now
        req.driver_id = user.id; req.status = 'accepted'; req.accepted_at = now
        db.session.flush()
        close_pending(req.id, 'cancelled', now)
        for other in DeliveryRequest.query.filter(DeliveryRequest.order_id == order.id,
                DeliveryRequest.id != req.id, DeliveryRequest.status == 'pending').order_by(
                DeliveryRequest.id).with_for_update().all():
            other.status = 'expired'; close_pending(other.id, 'cancelled', now)
    else:
        candidate.status = 'rejected'; candidate.responded_at = now
    db.session.commit()
    return req, order, True


def pending_for(user):
    if not user.is_active or not user.is_delivery:
        return []
    now = datetime.now(timezone.utc)
    rows = db.session.query(DeliveryRequestCandidate, DeliveryRequest).join(
        DeliveryRequest, DeliveryRequest.id == DeliveryRequestCandidate.delivery_request_id).join(
        Order, Order.id == DeliveryRequest.order_id).filter(
        DeliveryRequestCandidate.driver_id == user.id, DeliveryRequestCandidate.status == 'pending',
        DeliveryRequest.status == 'pending', Order.status == 'pending', Order.delivery_driver_id.is_(None)).all()
    result = []
    for candidate, req in rows:
        if req.is_expired() or not req.expires_at:
            continue
        expires = req.expires_at.replace(tzinfo=timezone.utc) if req.expires_at.tzinfo is None else req.expires_at
        result.append({'request': req, 'distance': candidate.approximate_distance_km,
                       'remaining': max(0, int((expires-now).total_seconds()))})
    return result


@rollback_on_error
def refresh_expiry(request_id):
    reference = db.session.get(DeliveryRequest, request_id)
    Order.query.filter_by(id=reference.order_id).populate_existing().with_for_update().first_or_404()
    req = DeliveryRequest.query.filter_by(id=request_id).populate_existing().with_for_update().first_or_404()
    if req.status == 'pending' and req.is_expired():
        req.status = 'expired'
        close_pending(req.id, 'expired', datetime.now(timezone.utc))
    db.session.commit()
    return req

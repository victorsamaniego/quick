import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects import postgresql
from werkzeug.exceptions import HTTPException
import test_order_destination
import routes
from models import db, User, Order, DeliveryRequest
from delivery_candidates import DeliveryRequestCandidate as Candidate, create_dispatch, respond, pending_for, refresh_expiry


class DeliveryCandidatesTest(unittest.TestCase):
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def setUp(self):
        test_order_destination.OrderDestinationTest.setUp(self)
        self.app.config['SECURITY_DELIVERY_CANDIDATES'] = True
        if self._testMethodName == 'test_http_rejection_requires_csrf_and_preserves_other_candidate':
            from extensions import csrf
            csrf.init_app(self.app)
        self.client.post('/order/create', data=self.checkout())
        self.order = Order.query.one()
        self.drivers = [User(username=f'candidate-{i}', email=f'candidate-{i}@example.test',
            phone='000000000', password_hash=self.buyer.password_hash, is_delivery=True) for i in range(3)]
        db.session.add_all(self.drivers); db.session.commit()
        self.nearby = patch.object(User, 'find_nearby_deliveries', return_value=[
            {'delivery': user, 'distance': 1.4+i} for i, user in enumerate(self.drivers[:2])])
        self.nearby.start(); self.addCleanup(self.nearby.stop)

    def dispatch(self):
        return create_dispatch(self.order.id, self.business.id, 5)[0]

    def assert_http(self, code, function, *args):
        with self.assertRaises(HTTPException) as caught: function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_reject_is_individual_then_other_accepts_and_retry_is_idempotent(self):
        req = self.dispatch(); first, second, outsider = self.drivers
        self.assertTrue(respond(req.id, first, False)[2])
        self.assertEqual(req.status, 'pending')
        self.assertEqual(pending_for(first), [])
        self.assertEqual(len(pending_for(second)), 1)
        self.assertFalse(respond(req.id, first, False)[2])
        self.assertTrue(respond(req.id, second, True)[2])
        self.assertEqual((self.order.status, self.order.delivery_driver_id), ('shipped', second.id))
        self.assertFalse(respond(req.id, second, True)[2])
        self.assert_http(409, respond, req.id, first, True)
        self.assert_http(403, respond, req.id, outsider, True)

    def test_one_winner_cancels_other_and_duplicate_dispatch_does_not_republish(self):
        self.login_as(self.seller)
        with patch.object(routes, 'publish') as publish:
            for _ in range(2):
                self.assertEqual(self.client.post(f'/admin/orders/{self.order.id}/request-delivery', data={'radius':'5'}).status_code, 302)
            self.assertEqual(publish.call_count, 2)
            payload = publish.call_args.args[1]
            for key in ('client_lat', 'client_lon', 'shipping_address', 'shipping_phone', 'buyer_name'):
                self.assertNotIn(key, payload)
        self.assertEqual(DeliveryRequest.query.count(), 1)
        self.assertEqual(Candidate.query.count(), 2)
        req = DeliveryRequest.query.one()
        self.login_as(self.drivers[0])
        with patch.object(routes, 'publish') as publish, patch.object(routes, 'publish_status') as status:
            for _ in range(2): self.assertEqual(self.client.post(f'/delivery-request/{req.id}/accept').status_code, 302)
            self.assertEqual(publish.call_count, 2); self.assertEqual(status.call_count, 1)
        self.assertEqual(Candidate.query.filter_by(driver_id=self.drivers[1].id).one().status, 'cancelled')
        self.assert_http(409, respond, req.id, self.drivers[1], True)

    def test_recipients_are_snapshot_not_new_neighbors_and_private_list(self):
        req = self.dispatch()
        with patch.object(User, 'find_nearby_deliveries', return_value=[{'delivery':self.drivers[2], 'distance':1}]):
            self.assertEqual(len(pending_for(self.drivers[0])), 1)
            self.assertEqual(pending_for(self.drivers[2]), [])
            self.assert_http(403, respond, req.id, self.drivers[2], False)
        self.login_as(self.drivers[0])
        response = self.client.get('/delivery-requests')
        self.assertEqual(response.status_code, 200)
        for secret in (self.order.shipping_address, self.order.shipping_phone, str(self.order.client_latitude)):
            self.assertNotIn(secret, response.text)

    def test_expired_and_legacy_requests_are_not_accepted_or_backfilled(self):
        req = self.dispatch(); req.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1); db.session.commit()
        self.assert_http(409, respond, req.id, self.drivers[0], True)
        self.assertEqual(pending_for(self.drivers[0]), [])
        refresh_expiry(req.id)
        self.assertEqual(req.status, 'expired')
        self.assertTrue(all(row.status == 'expired' for row in Candidate.query.all()))
        legacy = DeliveryRequest(order_id=self.order.id,business_id=self.business.id,search_radius=5,
                                 expires_at=datetime.now(timezone.utc)+timedelta(minutes=2),status='pending')
        db.session.add(legacy); db.session.commit()
        self.assert_http(409, create_dispatch, self.order.id, self.business.id, 5)
        self.assert_http(403, respond, legacy.id, self.drivers[0], True)
        self.assertEqual(Candidate.query.filter_by(delivery_request_id=legacy.id).count(), 0)

    def test_failed_commit_rolls_back_creation_and_assignment_without_events(self):
        self.login_as(self.seller)
        with patch.object(db.session, 'commit', side_effect=RuntimeError('synthetic failure')), patch.object(routes, 'publish') as publish:
            with self.assertRaises(RuntimeError): self.client.post(f'/admin/orders/{self.order.id}/request-delivery', data={'radius':'5'})
            publish.assert_not_called()
        self.assertEqual(DeliveryRequest.query.count(), 0); self.assertEqual(Candidate.query.count(), 0)
        req = self.dispatch(); self.login_as(self.drivers[0])
        with patch.object(db.session, 'commit', side_effect=RuntimeError('synthetic failure')), patch.object(routes, 'publish') as publish:
            with self.assertRaises(RuntimeError): self.client.post(f'/delivery-request/{req.id}/accept')
            publish.assert_not_called()
        self.assertIsNone(self.order.delivery_driver_id); self.assertEqual(req.status, 'pending')
        self.assertTrue(all(row.status == 'pending' for row in Candidate.query.all()))

    def test_wrong_business_inactive_driver_and_zero_destination(self):
        self.assert_http(403, create_dispatch, self.order.id, self.other.id, 5)
        self.order.client_latitude = 0; self.order.client_longitude = 0; db.session.commit()
        self.login_as(self.seller)
        self.assertEqual(self.client.get(f'/admin/orders/{self.order.id}/request-delivery').status_code, 200)
        req = self.dispatch()
        self.drivers[0].is_active = False; db.session.commit()
        self.assert_http(403, respond, req.id, self.drivers[0], True)
        self.assertEqual(pending_for(self.drivers[0]), [])

    def test_unique_winner_constraint_and_postgres_lock_sql(self):
        req = self.dispatch()
        rows = Candidate.query.all(); rows[0].status = 'accepted'; rows[1].status = 'accepted'
        with self.assertRaises(IntegrityError): db.session.commit()
        db.session.rollback()
        statement = str(Order.query.filter_by(id=self.order.id).with_for_update().statement.compile(dialect=postgresql.dialect()))
        self.assertIn('FOR UPDATE', statement)
        self.assertEqual(req.status, 'pending')

    def test_http_rejection_requires_csrf_and_preserves_other_candidate(self):
        import re
        req = self.dispatch(); self.login_as(self.drivers[0])
        response = self.client.get('/delivery-requests')
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)
        path = f'/delivery-request/{req.id}/reject'
        self.assertEqual(self.client.post(path).status_code, 400)
        self.assertEqual(Candidate.query.filter_by(driver_id=self.drivers[0].id).one().status, 'pending')
        with patch.object(routes, 'publish') as publish:
            self.assertEqual(self.client.post(path,data={'csrf_token':token}).status_code, 302)
            self.assertEqual(publish.call_count, 1)
        self.assertEqual(req.status, 'pending')
        self.assertEqual(len(pending_for(self.drivers[1])), 1)

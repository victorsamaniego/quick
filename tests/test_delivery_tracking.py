"""Tracking protocol and A/B/C audiences using only in-memory SQLite."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flask import g
from models import db, User, Order
from delivery_tracking import DeliveryLocation, tracking_snapshot
from realtime import publish_status
import test_realtime


class DeliveryTrackingTest(unittest.TestCase):
    setUp = test_realtime.RealtimeTest.setUp
    tearDown = test_realtime.RealtimeTest.tearDown
    connect = test_realtime.RealtimeTest.connect
    join = test_realtime.RealtimeTest.join
    messages = test_realtime.RealtimeTest.messages
    login_as = test_realtime.RealtimeTest.login_as
    checkout = test_realtime.RealtimeTest.checkout

    def order(self):
        order = test_realtime.RealtimeTest.create_order(self)
        order.status = 'shipped'
        db.session.commit()
        return order

    def emit(self, socket, order, **changes):
        g.pop('_login_user', None)
        return socket.emit('delivery_location_update', dict(order_id=order.id, latitude=-25.1,
                           longitude=-57.1, accuracy=10, **changes), callback=True)

    def test_assigned_driver_persists_and_only_abc_receive_once(self):
        order = self.order()
        sockets = [self.connect(user) for user in (self.buyer, self.seller, self.driver)]
        for sock in sockets: self.join(sock, f'order_{order.id}')
        other = self.connect(self.outsider)
        self.assertTrue(self.emit(sockets[2], order)['success'])
        self.assertEqual(DeliveryLocation.query.count(), 1)
        for sock in sockets:
            self.assertEqual(len(self.messages(sock, 'delivery_location_update')), 1)
        self.assertEqual(self.messages(other, 'delivery_location_update'), [])
        self.login_as(self.buyer)
        self.assertEqual(self.client.get(f'/api/orders/{order.id}/tracking').json['position']['latitude'], -25.1)

    def test_wrong_driver_buyer_and_business_cannot_transmit(self):
        order = self.order()
        outsider = User(email='candidate@example.test', phone='000', password_hash='test', is_delivery=True)
        db.session.add(outsider); db.session.commit()
        for user in (self.buyer, self.seller, outsider):
            self.assertFalse(self.emit(self.connect(user), order)['success'])
        self.assertEqual(DeliveryLocation.query.count(), 0)

    def test_pending_delivered_cancelled_and_unassigned_reject(self):
        order = self.order(); sock = self.connect(self.driver)
        for state in ('pending', 'delivered', 'cancelled'):
            order.status = state; db.session.commit()
            self.assertFalse(self.emit(sock, order)['success'])
        order.status = 'shipped'; order.delivery_driver_id = None; db.session.commit()
        self.assertFalse(self.emit(sock, order)['success'])

    def test_invalid_payloads_and_nonexistent_order(self):
        order = self.order(); sock = self.connect(self.driver)
        valid = dict(order_id=order.id, latitude=0, longitude=0, accuracy=10)
        bad = [None, [], {'padding': 'a' * 10000}]
        for key, value in [('latitude', None), ('latitude', float('nan')), ('longitude', float('inf')),
                           ('latitude', 91), ('longitude', -181), ('latitude', '0'), ('latitude', True),
                           ('accuracy', -1), ('accuracy', float('nan')), ('order_id', 9999),
                           ('order_id', True), ('user_id', self.driver.id), ('driver_id', self.driver.id),
                           ('buyer_id', self.buyer.id), ('business_id', self.business.id)]:
            bad.append({**valid, key: value})
        for data in bad:
            g.pop('_login_user', None)
            self.assertFalse(sock.emit('delivery_location_update', data, callback=True)['success'])
        self.assertEqual(DeliveryLocation.query.count(), 0)

    def test_snapshot_permissions_and_candidate_privacy(self):
        order = self.order()
        candidate = User(email='candidate@example.test', phone='000', password_hash='test', is_delivery=True)
        buyer = User(email='other-buyer@example.test', phone='000', password_hash='test')
        db.session.add_all([candidate, buyer]); db.session.commit()
        for user, expected in [(self.buyer, 200), (self.seller, 200), (self.driver, 200),
                               (self.outsider, 403), (candidate, 403), (buyer, 403), (self.admin, 403)]:
            self.login_as(user)
            for path in (f'/api/orders/{order.id}/tracking', f'/orders/{order.id}/tracking'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, expected)
                if expected == 403: self.assertNotIn(order.shipping_address, response.text)

    def test_waiting_stale_snapshot_and_reconnect(self):
        order = self.order()
        self.assertIsNone(tracking_snapshot(order, self.buyer)['position'])
        sock = self.connect(self.driver); self.emit(sock, order)
        row = DeliveryLocation.query.one(); row.updated_at -= timedelta(seconds=30); db.session.commit()
        self.assertTrue(tracking_snapshot(order, self.buyer)['stale'])
        sock.disconnect(); self.connect(self.driver)
        self.login_as(self.seller)
        response = self.client.get(f'/api/orders/{order.id}/tracking')
        self.assertTrue(response.json['stale']); self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertIsNotNone(response.json['pickup']); self.assertIsNotNone(response.json['dropoff'])

    def test_throttle_and_reassignment_hide_previous_position(self):
        order = self.order(); sock = self.connect(self.driver)
        self.assertTrue(self.emit(sock, order)['success'])
        self.assertEqual(self.emit(sock, order)['error'], 'throttled')
        order.delivery_driver_id = self.outsider.id; db.session.commit()
        self.assertIsNone(tracking_snapshot(order, self.buyer)['position'])
        self.assertFalse(self.emit(sock, order)['success'])

    def test_delivered_stops_updates_and_live_snapshot(self):
        order = self.order(); sock = self.connect(self.driver); buyer = self.connect(self.buyer)
        self.emit(sock, order)
        self.login_as(self.driver)
        self.assertEqual(self.client.post(f'/delivery/order/{order.id}/mark-delivered').status_code, 302)
        self.assertFalse(self.emit(sock, order)['success'])
        self.assertFalse(tracking_snapshot(order, self.buyer)['active'])
        self.assertEqual(self.messages(buyer, 'order_status_update')[0]['status'], 'delivered')

    def test_buttons_only_for_assigned_active_order(self):
        order = self.order()
        for status, assigned, visible in [('shipped', True, True), ('pending', True, False),
                                           ('delivered', True, False), ('cancelled', True, False), ('shipped', False, False)]:
            order.status = status; order.delivery_driver_id = self.driver.id if assigned else None; db.session.commit()
            for user, path in [(self.buyer, '/dashboard'), (self.seller, '/admin/orders')]:
                self.login_as(user)
                self.assertEqual(f'data-tracking-link="{order.id}"' in self.client.get(path).text, visible)

    def test_abc_dispatch_three_positions_then_delivery(self):
        from delivery_candidates import create_dispatch
        order = test_realtime.RealtimeTest.create_order(self)
        order.delivery_driver_id = None; db.session.commit()
        self.app.config['SECURITY_DELIVERY_CANDIDATES'] = True
        a, b, c = [self.connect(user) for user in (self.buyer, self.seller, self.driver)]
        with patch.object(User, 'find_nearby_deliveries', return_value=[{'delivery': self.driver, 'distance': 1}]):
            self.login_as(self.seller)
            self.client.post(f'/admin/orders/{order.id}/request-delivery', data={'radius': '5'})
        req = self.messages(c, 'new_delivery_request')[0]['request_id']
        self.login_as(self.driver)
        self.assertEqual(self.client.post(f'/delivery-request/{req}/accept').status_code, 302)
        self.assertEqual(order.status, 'shipped')
        for latitude in (-25.01, -25.02, -25.03):
            row = db.session.get(DeliveryLocation, order.id)
            if row: row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=6); db.session.commit()
            g.pop('_login_user', None)
            self.assertTrue(c.emit('delivery_location_update', {'order_id': order.id, 'latitude': latitude,
                                 'longitude': -57.02, 'accuracy': 5}, callback=True)['success'])
            for sock in (a, b):
                self.assertEqual(self.messages(sock, 'delivery_location_update')[-1]['latitude'], latitude)
        self.login_as(self.driver)
        self.client.post(f'/delivery/order/{order.id}/mark-delivered')
        for sock in (a, b):
            self.assertEqual(self.messages(sock, 'order_status_update')[-1]['status'], 'delivered')
        self.assertFalse(self.emit(c, order)['success'])

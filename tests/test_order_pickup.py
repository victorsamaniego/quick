"""Store pickup integration: isolated SQLite and real existing transports."""
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import event
from extensions import csrf
from models import db, Order, DeliveryRequest, Product
from delivery_tracking import save_location, tracking_snapshot
from realtime import publish_status
import test_realtime
import web_push


class StorePickupTest(unittest.TestCase):
    def setUp(self):
        test_realtime.RealtimeTest.setUp(self)
        self.other.requires_subscription = False
        db.session.commit()
    tearDown = test_realtime.RealtimeTest.tearDown
    login_as = test_realtime.RealtimeTest.login_as
    checkout = test_realtime.RealtimeTest.checkout
    connect = test_realtime.RealtimeTest.connect
    messages = test_realtime.RealtimeTest.messages

    def order(self, status='pending', assigned=False):
        order = Order(user_id=self.buyer.id, business_id=self.business.id,
                      total_amount=100, shipping_address='Local', shipping_phone='000',
                      status=status, delivery_driver_id=self.driver.id if assigned else None)
        db.session.add(order)
        db.session.commit()
        self.login_as(self.seller)
        return order

    def pickup(self, order, **kwargs):
        return self.client.post(f'/admin/orders/{order.id}/pick-up', **kwargs)

    def test_owner_persistence_timestamp_and_notifications_after_commit(self):
        order = self.order()
        buyer, seller = self.connect(self.buyer), self.connect(self.seller)
        self.login_as(self.seller)
        committed = []
        def after_commit(session):
            committed.append(True)
        event.listen(db.session(), 'after_commit', after_commit)
        def check_publish(order, old):
            self.assertTrue(committed)
            self.assertFalse(db.session.dirty)
            return publish_status(order, old)
        with patch('routes.publish_status', side_effect=check_publish), patch('web_push.enqueue') as enqueue:
            self.assertEqual(self.pickup(order).status_code, 200)
            self.assertTrue(committed)
            args = enqueue.call_args.args
            self.assertEqual(args[0], 'order_status_update')
            self.assertEqual(args[1]['status'], 'picked_up')
            self.assertIn(f'user_{self.buyer.id}', args[2])
            self.assertIn(f'business_{self.business.id}', args[2])
        event.remove(db.session(), 'after_commit', after_commit)
        db.session.expire_all()
        self.assertEqual(order.status, 'picked_up')
        self.assertIsNotNone(order.picked_up_at)
        self.assertLess(abs((datetime.now(timezone.utc) - order.picked_up_at.replace(tzinfo=timezone.utc)).total_seconds()), 10)
        self.assertIsNone(order.delivered_at)
        for sock in (buyer, seller):
            self.assertEqual(self.messages(sock, 'order_status_update')[0]['status'], 'picked_up')

    def test_other_seller_cannot_spoof_business(self):
        order = self.order()
        self.login_as(self.outsider)
        self.assertEqual(self.pickup(order, data={'business_id': self.business.id}).status_code, 403)
        self.assertEqual(order.status, 'pending')

    def test_buyer_and_missing_order(self):
        order = self.order()
        self.login_as(self.buyer)
        self.assertEqual(self.pickup(order).status_code, 302)
        self.assertEqual(order.status, 'pending')
        self.login_as(self.seller)
        self.assertEqual(self.client.post('/admin/orders/999999/pick-up').status_code, 404)

    def test_invalid_transitions_and_assigned_driver(self):
        for status, assigned in [('cancelled', False), ('delivered', False), ('picked_up', False),
                                 ('shipped', False), ('pending', True), ('unknown', False)]:
            with self.subTest(status=status, assigned=assigned):
                order = self.order(status, assigned)
                with patch('routes.publish_status') as publish:
                    self.assertEqual(self.pickup(order).status_code, 409)
                    publish.assert_not_called()
                self.assertEqual(order.status, status)

    def test_repeat_and_generic_endpoint_cannot_reopen(self):
        order = self.order()
        self.assertEqual(self.pickup(order).status_code, 200)
        timestamp = order.picked_up_at
        with patch('routes.publish_status') as publish:
            self.assertEqual(self.pickup(order).status_code, 409)
            for status in ['pending', 'shipped', 'delivered', 'cancelled']:
                self.assertEqual(self.client.post(f'/admin/orders/{order.id}/update-status', data={'status': status}).status_code, 409)
            publish.assert_not_called()
        self.assertEqual(order.picked_up_at, timestamp)

    def test_failed_commit_has_no_notification(self):
        order = self.order()
        with patch.object(db.session, 'commit', side_effect=RuntimeError('test commit failure')), patch('routes.publish_status') as publish, patch('web_push.enqueue') as enqueue:
            with self.assertRaises(RuntimeError):
                self.pickup(order)
            publish.assert_not_called()
            enqueue.assert_not_called()
        db.session.expire_all()
        self.assertEqual(order.status, 'pending')
        self.assertIsNone(order.picked_up_at)

    def test_csrf(self):
        order = self.order()
        csrf.init_app(self.app)
        self.assertEqual(self.pickup(order).status_code, 400)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', self.client.get('/admin/orders').text).group(1)
        self.assertEqual(self.pickup(order, data={'csrf_token': token}).status_code, 200)

    def test_dispatch_blocks_until_expiry_then_cannot_accept(self):
        order = self.order()
        req = DeliveryRequest(order_id=order.id, business_id=order.business_id, search_radius=5,
                              expires_at=datetime.now(timezone.utc) + timedelta(minutes=2))
        db.session.add(req); db.session.commit()
        self.assertEqual(self.pickup(order).status_code, 409)
        req.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        self.assertEqual(self.pickup(order).status_code, 200)
        # Even a stale request with a renewed expiry cannot take a completed order.
        req.expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        db.session.commit()
        self.login_as(self.driver)
        self.assertEqual(self.client.post(f'/delivery-request/{req.id}/accept').status_code, 403)
        self.assertEqual(order.status, 'picked_up')

    def test_tracking_and_delivery_active_list(self):
        order = self.order('picked_up', assigned=True)  # Defensive against inconsistent historical data.
        self.assertFalse(order.tracking_active)
        self.assertFalse(tracking_snapshot(order, self.driver)['can_transmit'])
        result = save_location({'order_id': order.id, 'latitude': -25, 'longitude': -57, 'accuracy': 5}, self.driver)
        self.assertEqual(result['error'], 'inactive')
        self.login_as(self.driver)
        captured = {}
        def render(template, **context):
            captured.update(context)
            return 'ok'
        with patch('routes.render_template', side_effect=render):
            self.assertEqual(self.client.get('/delivery/dashboard').status_code, 200)
        self.assertNotIn(order, captured['delivery_orders'])
        self.assertEqual(captured['total_deliveries'], 0)
        self.assertEqual(self.client.post(f'/delivery/order/{order.id}/mark-delivered').status_code, 409)

    def test_templates_and_sales(self):
        order = self.order()
        stock = Product.query.first().stock
        self.pickup(order)
        self.assertEqual(Product.query.first().stock, stock)
        self.assertEqual(self.business.revenue_last_30_days, 100)
        for user, url in [(self.seller, '/admin/orders?status=picked_up'), (self.buyer, '/dashboard'),
                          (self.admin, '/super-admin/'), (self.admin, f'/super-admin/businesses/{self.business.id}/view')]:
            self.login_as(user)
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200, url)
            self.assertIn('Retirado del local', page.text)
            self.assertNotIn('data-store-pickup', page.text)
        self.login_as(self.seller)
        captured = {}
        with patch('routes.render_template', side_effect=lambda template, **kw: captured.update(kw) or 'ok'):
            self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertEqual(captured['total_sales'], 100)
        self.assertIn(['picked_up', 1], captured['orders_by_status'])
        from analytics_service import analytics_data
        data = analytics_data()
        self.assertEqual(data['revenue_by_business'][0]['revenue'], 100)
        self.assertEqual(data['order_statuses'][0]['status'], 'picked_up')
        self.assertEqual(data['order_statuses'][0]['status_label'], 'Retirado del local')

    def test_push_payload_and_enabled_gate(self):
        order = self.order()
        with self.app.test_request_context('/'):
            payload = web_push.push_payload('order_status_update', {'order_id': order.id, 'status': 'picked_up'}, self.buyer)
            self.assertEqual(payload['title'], 'Pedido retirado')
            self.assertIn('retirado del local', payload['body'])
            self.app.config['WEB_PUSH_ENABLED'] = False
            with patch.object(web_push._executor, 'submit') as submit:
                web_push.enqueue('order_status_update', {'order_id': order.id, 'status': 'picked_up'}, [f'user_{self.buyer.id}'])
                submit.assert_not_called()

    def test_candidate_dispatch_cannot_take_picked_up(self):
        from delivery_candidates import DeliveryRequestCandidate, pending_for
        order = self.order('picked_up')
        req = DeliveryRequest(order_id=order.id, business_id=order.business_id, search_radius=5,
                              expires_at=datetime.now(timezone.utc) + timedelta(minutes=2))
        db.session.add(req); db.session.flush()
        db.session.add(DeliveryRequestCandidate(delivery_request_id=req.id, driver_id=self.driver.id,
                                               approximate_distance_km=1, notified_at=datetime.now(timezone.utc)))
        db.session.commit()
        self.app.config['SECURITY_DELIVERY_CANDIDATES'] = True
        self.login_as(self.driver)
        self.assertEqual(pending_for(self.driver), [])
        self.assertEqual(self.client.post(f'/delivery-request/{req.id}/accept').status_code, 409)
        self.assertEqual(order.status, 'picked_up')

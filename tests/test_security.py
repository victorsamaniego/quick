"""Security regressions, using only the existing in-memory SQLite fixture."""
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flask import Flask
from werkzeug.exceptions import BadRequest
import test_order_destination
from models import db, Product, Order, OrderItem, User, OTPCode, ChatMessage, DeliveryRequest
import routes
from security import bounded_decimal, is_safe_redirect_url


class InputSecurityTest(unittest.TestCase):
    def test_redirect_allowlist(self):
        with Flask(__name__).test_request_context('/', base_url='https://quickgo.test'):
            for target in ['/dashboard', '/products?q=x', 'https://quickgo.test/cart']:
                self.assertTrue(is_safe_redirect_url(target), target)
            for target in ['https://evil.test', '//evil.test', '/\\evil.test', '/%5cevil.test',
                           '/%2fevil.test', 'javascript:alert(1)', 'data:text/html,x',
                           '\n//evil.test', '/%0a/evil.test', 'https://quickgo.test@evil.test', None]:
                self.assertFalse(is_safe_redirect_url(target), target)

    def test_money_rejects_nonfinite_negative_huge_and_boolean(self):
        for value in ['NaN', 'Infinity', '-Infinity', '-1', '1000000001', {}, True, '1e999999']:
            with self.assertRaises(BadRequest):
                bounded_decimal(value)
        self.assertEqual(str(bounded_decimal('12.50')), '12.50')

    def test_legacy_otp_repr_and_expiration(self):
        value = OTPCode.generate_code()
        self.assertEqual(len(value), 6)
        otp = OTPCode(user_id=1, code=value, purpose='test', created_at=datetime.now(timezone.utc))
        self.assertNotIn(value, repr(otp))
        self.assertFalse(otp.is_expired())
        otp.used = True
        self.assertTrue(otp.is_expired())
        otp.used = False
        otp.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=11)
        self.assertTrue(otp.is_expired())


class CheckoutSecurityTest(unittest.TestCase):
    setUp = test_order_destination.OrderDestinationTest.setUp
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def test_mixed_cart_rejected_without_any_writes(self):
        data = self.checkout()
        product = Product.query.one()
        other = Product(name='Other', business_id=self.other.id, stock=10, price=100)
        db.session.add(other); db.session.commit()
        with self.client.session_transaction() as session:
            session['cart'] = {**session['cart'], str(other.id): 1}
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(OrderItem.query.count(), 0)
        self.assertEqual((product.stock, other.stock), (3, 10))

    def test_add_and_update_cannot_mix_businesses(self):
        self.login_as(self.buyer)
        product = Product.query.one()
        other = Product(name='Other', business_id=self.other.id, stock=10, price=100)
        db.session.add(other); db.session.commit()
        self.client.post(f'/cart/add/{product.id}')
        self.client.post(f'/cart/add/{other.id}')
        self.client.post(f'/cart/update/{other.id}', data={'action': 'increase'})
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'], {str(product.id): 1})
            self.assertEqual(session['cart_business_id'], self.business.id)

    def test_insufficient_stock_rejects_entire_order(self):
        data = self.checkout()
        product = Product.query.one()
        with self.client.session_transaction() as session:
            session['cart'] = {str(product.id): product.stock + 1}
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(product.stock, 3)

    def test_negative_quantity_rejected(self):
        data = self.checkout()
        with self.client.session_transaction() as session:
            session['cart'] = {str(Product.query.one().id): -1}
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.assertEqual(Product.query.one().stock, 3)

    def test_failed_commit_rolls_back_stock_without_caller_rollback(self):
        data = self.checkout()
        with patch.object(db.session, 'commit', side_effect=RuntimeError('isolated test')):
            with self.assertRaises(RuntimeError):
                self.client.post('/order/create', data=data)
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(OrderItem.query.count(), 0)
        self.assertEqual(Product.query.one().stock, 3)

    def test_checkout_locks_sorted_products_and_keeps_purchase_price(self):
        from sqlalchemy import event
        statements = []
        def observe(state):
            if getattr(state.statement, '_for_update_arg', None) is not None:
                statements.append(state.statement)
        data = self.checkout()
        event.listen(db.session(), 'do_orm_execute', observe)
        try:
            self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        finally:
            event.remove(db.session(), 'do_orm_execute', observe)
        from sqlalchemy.dialects import postgresql
        sql = [str(stmt.compile(dialect=postgresql.dialect())) for stmt in statements]
        self.assertTrue(any('ORDER BY products.id FOR UPDATE' in item for item in sql))
        self.assertEqual(Product.query.one().stock, 2)
        self.assertEqual(OrderItem.query.one().price_at_purchase, 100)

    def test_cash_nonfinite_input_rejected_without_writes(self):
        data = self.checkout()
        for value in ['NaN', 'Infinity', '-1', '1000000001']:
            self.assertEqual(self.client.post('/order/create', data={**data, 'cash_bill_amount': value}).status_code, 400)
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(Product.query.one().stock, 3)

    def test_location_validation_preserves_zero_and_rejects_invalid(self):
        driver = User(username='driver-security', email='driver@example.test', phone='000',
                      password_hash=self.buyer.password_hash, is_delivery=True)
        db.session.add(driver); db.session.commit(); self.login_as(driver)
        for payload in [[], {'latitude': 'NaN', 'longitude': 0}, {'latitude': 91, 'longitude': 0},
                        {'latitude': 0, 'longitude': 181}, {'latitude': 0, 'longitude': 0, 'user_id': 1}]:
            self.assertEqual(self.client.post('/delivery/api/location/update', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/delivery/api/location/update', json={'latitude': 0, 'longitude': 0}).status_code, 200)
        self.assertEqual((driver.latitude, driver.longitude), (0, 0))

    def test_chat_limit_and_delivery_fee_validation(self):
        data = self.checkout(); self.client.post('/order/create', data=data)
        order = Order.query.one(); original = order.total_amount
        self.assertEqual(self.client.post(f'/api/chat/order/{order.id}/send', json={'message': 'x' * 2001}).status_code, 400)
        self.assertEqual(ChatMessage.query.count(), 0)
        self.login_as(self.seller)
        for value in ['NaN', 'Infinity', -1, 1000000001]:
            self.assertEqual(self.client.post(f'/admin/pedido/{order.id}/actualizar-delivery', json={'delivery_fee': value}).status_code, 400)
            self.assertEqual(order.total_amount, original)

    def test_delivery_candidate_has_no_address_but_assigned_has_it(self):
        data = self.checkout(); self.client.post('/order/create', data=data)
        order = Order.query.one()
        driver = User(username='candidate', email='candidate@example.test', phone='000',
                      password_hash=self.buyer.password_hash, is_delivery=True)
        db.session.add(driver); db.session.commit(); self.login_as(self.seller)
        with patch.object(User, 'find_nearby_deliveries', return_value=[{'delivery': driver, 'distance': 1.25}]), patch.object(routes, 'publish') as publish:
            self.client.post(f'/admin/orders/{order.id}/request-delivery', data={'radius': 5})
            self.assertTrue(publish.called)
            payload = publish.call_args.args[1]
            for key in ['delivery_address', 'shipping_address', 'shipping_reference', 'phone', 'client_latitude', 'client_longitude']:
                self.assertNotIn(key, payload)
            self.login_as(driver)
            page = self.client.get('/delivery-requests')
            self.assertNotIn(order.shipping_address, page.text)
            self.assertNotIn(order.shipping_reference, page.text)
            self.assertEqual(self.client.get(f'/delivery/order/{order.id}').status_code, 302)
            self.client.post(f'/delivery-request/{DeliveryRequest.query.one().id}/accept')
        self.assertEqual(order.delivery_driver_id, driver.id)
        self.assertIn(order.shipping_address, self.client.get(f'/delivery/order/{order.id}').text)

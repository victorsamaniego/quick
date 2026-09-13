import re
import unittest
from pathlib import Path
import test_order_destination
import test_realtime
from extensions import csrf
from models import db, Product, Order


class StorefrontTest(unittest.TestCase):
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def setUp(self):
        test_order_destination.OrderDestinationTest.setUp(self)
        csrf.init_app(self.app)
        self.app.config['SECURITY_ENFORCE_COVERAGE'] = True

    def token(self):
        page = self.client.get('/admin/')
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)

    def test_status_ownership_csrf_and_independent_activation(self):
        token = self.token()
        url = '/admin/business/status'
        self.assertEqual(self.client.post(url, data={'is_open': 'false'}).status_code, 400)
        for extra in ({'business_id': self.other.id}, {'is_active': 'false'}):
            self.assertEqual(self.client.post(url, data={'csrf_token': token, 'is_open': 'false', **extra}).status_code, 403)
        for value in ('false', 'true'):
            self.assertEqual(self.client.post(url, data={'csrf_token': token, 'is_open': value}).status_code, 302)
            self.assertEqual(self.business.is_open, value == 'true')
            self.assertTrue(self.business.is_active)
            self.assertTrue(self.other.is_open)
        self.login_as(self.buyer)
        self.assertEqual(self.client.post(url, data={'csrf_token': token, 'is_open': 'false'}).status_code, 302)

    def test_closed_add_and_checkout_preserve_inventory(self):
        data = self.checkout()
        product = Product.query.filter_by(business_id=self.business.id).one()
        self.business.is_open = False
        db.session.commit()
        for url, payload in [(f'/cart/add/{product.id}', {'csrf_token': data['csrf_token']}), ('/order/create', data)]:
            response = self.client.post(url, data=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn('cerrado', response.text)
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(product.stock, 3)
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'][str(product.id)], 1)

    def test_normal_radius_and_gold_bypass_still_require_open(self):
        data = self.checkout('0', '0')
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.business.is_quickgold = True
        self.business.is_open = False
        db.session.commit()
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.business.is_open = True
        db.session.commit()
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        self.assertEqual(Order.query.count(), 1)

    def test_checkout_only_decrements_own_product(self):
        other_product = Product(name='Private inventory B', business_id=self.other.id, price=999, stock=714)
        db.session.add(other_product)
        db.session.commit()
        data = self.checkout()
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        self.assertEqual(other_product.stock, 714)
        self.assertEqual(Product.query.filter_by(business_id=self.business.id).one().stock, 2)
        self.login_as(self.seller)
        self.assertEqual(self.client.post(f'/admin/products/{other_product.id}/edit', data={
            'csrf_token': self.token(), 'stock': '1', 'price': '1', 'name': 'Hacked'}).status_code, 302)
        self.assertEqual(other_product.stock, 714)
        self.assertNotIn('Private inventory B', self.client.get('/admin/inventory').text)

    def test_fixed_location_validations_and_user_unchanged(self):
        token = self.token()
        url = '/admin/business/location'
        headers = {'X-CSRFToken': token}
        before = self.seller.latitude, self.seller.longitude
        self.assertEqual(self.client.post(url, json={'latitude': 0, 'longitude': 0}).status_code, 400)
        self.assertEqual(self.client.post(url, json={'latitude': 0, 'longitude': 0, 'business_id': self.other.id}, headers=headers).status_code, 403)
        for lat, lon in [(91, 0), (0, 181), ('nan', 0), (0, 'inf'), (None, 0)]:
            self.assertEqual(self.client.post(url, json={'latitude': lat, 'longitude': lon}, headers=headers).status_code, 400)
        for lat, lon in [(-90, -180), (90, 180), (0, 0), (-25, -57)]:
            response = self.client.post(url, json={'latitude': lat, 'longitude': lon}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual((self.business.latitude, self.business.longitude), (lat, lon))
        self.assertEqual((self.seller.latitude, self.seller.longitude), before)
        self.assertEqual((self.other.latitude, self.other.longitude), (0, 0))
        page = self.client.get('/admin/').text
        self.assertNotIn('name="latitude"', page)
        self.assertNotIn('name="longitude"', page)

    def test_radius_without_coordinates_preserves_fixed_location(self):
        token = self.token()
        data = {'csrf_token': token, 'address': 'Clorinda', 'delivery_radius_km': '50'}
        self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 302)
        self.assertEqual((self.business.latitude, self.business.longitude), (-25, -57))
        self.assertEqual(self.business.delivery_radius_km, 50)
        for radius in ('nan', '999', '-1'):
            self.assertEqual(self.client.post('/admin/business/coverage', data={**data, 'delivery_radius_km': radius}).status_code, 400)

    def test_open_add_inside_radius_and_closed_detail(self):
        token = self.token()
        self.login_as(self.buyer)
        with self.client.session_transaction() as session:
            session['user_location'] = {'latitude': -25, 'longitude': -57}
        product = Product.query.filter_by(business_id=self.business.id).one()
        self.assertEqual(self.client.post(f'/cart/add/{product.id}', data={'csrf_token': token}).status_code, 302)
        self.business.is_open = False
        db.session.commit()
        response = self.client.get(f'/product/{product.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cerrado', response.text)
        self.assertNotIn('type="submit"', response.text)

    def test_public_stock_is_not_rendered(self):
        for name in ('products.html', 'product_detail.html', 'dashboard.html'):
            source = (Path(__file__).parents[1] / 'templates' / name).read_text(encoding='utf-8')
            self.assertNotRegex(source, r'\{\{\s*product\.stock')
        self.business.is_open = False
        db.session.commit()
        self.login_as(self.buyer)
        with self.client.session_transaction() as session:
            session['user_latitude'], session['user_longitude'] = -25, -57
        response = self.client.get('/products')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cerrado', response.text)

    def test_production_enforces_coverage_even_with_legacy_flag_false(self):
        import os
        import secrets
        from flask import Flask
        from unittest.mock import patch
        from runtime_security import configure_runtime_security
        app = Flask('production-config-test')
        app.secret_key = secrets.token_urlsafe(40)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        with patch.dict(os.environ, {'FLASK_ENV': 'production', 'FLASK_DEBUG': '0', 'SECURITY_ENFORCE_COVERAGE': 'false'}, clear=True):
            configure_runtime_security(app)
        self.assertTrue(app.config['SECURITY_ENFORCE_COVERAGE'])


class StorefrontRealtimeTest(unittest.TestCase):
    setUp = test_realtime.RealtimeTest.setUp
    tearDown = test_realtime.RealtimeTest.tearDown
    connect = test_realtime.RealtimeTest.connect
    login_as = test_realtime.RealtimeTest.login_as
    messages = test_realtime.RealtimeTest.messages

    def test_status_reaches_buyer_once_without_private_inventory(self):
        buyer_socket = self.connect(self.buyer)
        self.login_as(self.seller)
        self.assertEqual(self.client.post('/admin/business/status', data={'is_open': 'false'}).status_code, 302)
        messages = self.messages(buyer_socket, 'business_status_update')
        self.assertEqual(messages, [{'business_id': self.business.id, 'is_open': False, 'is_active': True}])
        self.login_as(self.buyer)
        response = self.client.get(f'/api/business-status?ids={self.business.id}')
        self.assertEqual(response.json, {str(self.business.id): {'is_open': False, 'is_active': True}})
        self.assertIn('no-store', response.headers['Cache-Control'])

import re
import unittest
import test_merchant_coverage
from models import db, Order, Product, User


class OrderDestinationTest(unittest.TestCase):
    setUp = test_merchant_coverage.MerchantCoverageTest.setUp
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as

    def checkout(self, lat='-25.01', lon='-57.02'):
        self.login_as(self.buyer)
        with self.client.session_transaction() as session:
            session['cart'] = {str(Product.query.filter_by(business_id=self.business.id).first().id): 1}
            session['user_location'] = {'latitude': -24, 'longitude': -56}
        page = self.client.get('/order/create')
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
        self.assertIsNotNone(token)
        return dict(csrf_token=token.group(1), client_latitude=lat, client_longitude=lon,
                    destination_confirmed='yes', shipping_address='Trabajo, puerta principal',
                    shipping_phone='0981000000', shipping_reference='Portón azul', payment_method='cash')

    def test_current_location_persists(self):
        data = self.checkout('-24', '-56')
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        order = Order.query.one()
        self.assertEqual((order.client_latitude, order.client_longitude, order.user_id), (-24, -56, self.buyer.id))
        self.assertEqual(order.shipping_reference, 'Portón azul')

    def test_manual_point_ignores_session_and_later_gps(self):
        data = self.checkout()
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        order_id = Order.query.one().id
        self.assertEqual(self.client.post('/api/location/update', json={'latitude': -20, 'longitude': -50}).status_code, 200)
        db.session.remove()
        order = db.session.get(Order, order_id)
        self.assertEqual((order.client_latitude, order.client_longitude), (-25.01, -57.02))
        self.assertEqual(order.shipping_address, 'Trabajo, puerta principal')
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Punto de entrega guardado: -25.01, -57.02', response.text)

    def test_other_buyer_cannot_change_existing_destination(self):
        data = self.checkout()
        self.client.post('/order/create', data=data)
        order = Order.query.one()
        other_buyer = User(username='other-buyer', email='other-buyer@example.test',
                           phone='000000000', password_hash=self.buyer.password_hash)
        db.session.add(other_buyer)
        db.session.commit()
        self.login_as(other_buyer)
        for extra in ({'order_id': order.id}, {'user_id': self.buyer.id}, {'status': 'delivered'}):
            response = self.client.post('/api/location/update', json={'latitude': 0, 'longitude': 0, **extra})
            self.assertEqual(response.status_code, 400)
        db.session.expire_all()
        self.assertEqual((order.client_latitude, order.client_longitude), (-25.01, -57.02))

    def test_seller_and_assigned_delivery_use_saved_destination(self):
        data = self.checkout()
        self.client.post('/order/create', data=data)
        order = Order.query.one()
        driver = User(username='driver-test', email='driver@example.test', phone='000000000',
                      password_hash=self.buyer.password_hash, is_delivery=True)
        db.session.add(driver)
        db.session.flush()
        order.delivery_driver_id = driver.id
        db.session.commit()
        self.login_as(self.seller)
        response = self.client.get(f'/admin/api/orders/{order.id}/location')
        self.assertEqual(response.status_code, 200)
        self.assertIn('-25.01', response.text)
        self.assertIn('-57.02', response.text)
        self.login_as(driver)
        response = self.client.get(f'/delivery/order/{order.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('-25.01', response.text)
        self.assertIn('-57.02', response.text)

    def test_invalid_coordinates_and_confirmation_rejected(self):
        for latitude, longitude in [('91', '0'), ('0', '181'), ('nan', '0'), ('0', 'inf'), ('bad', '0'), ('', '0')]:
            data = self.checkout(latitude, longitude)
            self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
            self.assertEqual(Order.query.count(), 0)
        data = self.checkout()
        data['destination_confirmed'] = ''
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.assertEqual(Order.query.count(), 0)

    def test_extra_fields_rejected_before_order_creation(self):
        for key in ('order_id', 'user_id', 'status', 'is_admin', 'is_quickgold'):
            data = self.checkout()
            data[key] = '1'
            self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
            self.assertEqual(Order.query.count(), 0)

    def test_zero_coordinates_cart_and_stock(self):
        data = self.checkout('0', '0')
        product = Product.query.filter_by(business_id=self.business.id).first()
        before = product.stock
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        order = Order.query.one()
        self.assertEqual((order.client_latitude, order.client_longitude), (0, 0))
        self.assertEqual(product.stock, before - 1)
        self.assertEqual(len(order.items_list), 1)
        with self.client.session_transaction() as session:
            self.assertNotIn('cart', session)

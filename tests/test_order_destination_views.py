import unittest
import test_order_destination
from models import db, Order, User


class OrderDestinationViewsTest(unittest.TestCase):
    setUp = test_order_destination.OrderDestinationTest.setUp
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def create_assigned_order(self):
        data = self.checkout()
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        order = Order.query.one()
        driver = User(username='views-driver', email='views-driver@example.test', phone='000000000',
                      password_hash=self.buyer.password_hash, is_delivery=True)
        db.session.add(driver)
        db.session.flush()
        order.delivery_driver_id = driver.id
        db.session.commit()
        return order, driver

    def assert_destination_views(self, order, driver, missing=False):
        for user, url in ((self.buyer, '/dashboard'),
                          (self.seller, f'/admin/pedido/{order.id}/ubicacion'),
                          (driver, f'/delivery/order/{order.id}')):
            self.login_as(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn(order.shipping_address, response.text)
            self.assertIn(order.shipping_reference, response.text)
            if missing:
                self.assertIn('Ubicación de entrega no disponible', response.text)
                self.assertNotIn('data-order-destination', response.text)
            else:
                self.assertIn(f'data-latitude="{order.client_latitude}"', response.text)
                self.assertIn(f'data-longitude="{order.client_longitude}"', response.text)
                self.assertIn('js/order_destination_map.js', response.text)

    def test_three_roles_see_saved_map_after_reload(self):
        order, driver = self.create_assigned_order()
        self.assert_destination_views(order, driver)
        self.login_as(self.buyer)
        self.client.post('/api/location/update', json={'latitude': -21, 'longitude': -51})
        db.session.expire_all()
        self.assertEqual((order.client_latitude, order.client_longitude), (-25.01, -57.02))
        self.assert_destination_views(order, driver)

    def test_legacy_missing_and_partial_coordinates(self):
        order, driver = self.create_assigned_order()
        for lat, lon in ((None, None), (None, -57), (-25, None)):
            order.client_latitude, order.client_longitude = lat, lon
            db.session.commit()
            self.assert_destination_views(order, driver, missing=True)

    def test_zero_coordinates_are_valid_destinations(self):
        order, driver = self.create_assigned_order()
        order.client_latitude = order.client_longitude = 0
        db.session.commit()
        self.assert_destination_views(order, driver)

    def test_unrelated_users_do_not_receive_private_destination(self):
        order, driver = self.create_assigned_order()
        outsider = User(username='views-outsider', email='views-outsider@example.test', phone='000000000',
                        password_hash=self.buyer.password_hash)
        db.session.add(outsider)
        db.session.commit()
        self.login_as(outsider)
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(order.shipping_address, response.text)
        self.assertEqual(self.client.post('/api/location/update', json={
            'order_id': order.id, 'latitude': 0, 'longitude': 0
        }).status_code, 400)
        self.assertEqual(self.client.get(f'/admin/pedido/{order.id}/ubicacion').status_code, 302)
        self.assertEqual(self.client.get(f'/delivery/order/{order.id}').status_code, 302)
        outsider.is_admin = True
        outsider.business_id = self.other.id
        db.session.commit()
        self.login_as(outsider)
        self.assertEqual(self.client.get(f'/admin/pedido/{order.id}/ubicacion').status_code, 302)
        self.assertEqual(self.client.get(f'/admin/api/pedido/{order.id}/datos').status_code, 403)
        outsider.is_admin = False
        outsider.is_delivery = True
        db.session.commit()
        self.login_as(outsider)
        response = self.client.get(f'/delivery/order/{order.id}')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(order.shipping_address, response.text)
        db.session.expire_all()
        self.assertEqual((order.client_latitude, order.client_longitude), (-25.01, -57.02))

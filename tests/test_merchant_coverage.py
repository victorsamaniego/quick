import re
from flask import g
import unittest
import test_radio
from models import db, User, Business
import routes


class MerchantCoverageTest(unittest.TestCase):
    tearDown = test_radio.CoverageTest.tearDown
    check_distance = test_radio.CoverageTest.check_distance

    def setUp(self):
        test_radio.CoverageTest.setUp(self)
        self.app.register_blueprint(routes.admin_bp)
        self.app.register_blueprint(routes.delivery_bp)
        self.business.requires_subscription = False
        self.other = Business(name='Other shop', slug='other', latitude=0, longitude=0, delivery_radius_km=10)
        self.seller = User(username='seller-test', email='seller@example.test', phone='000000000',
                           password_hash=self.buyer.password_hash, is_admin=True, business_id=self.business.id)
        db.session.add_all([self.other, self.seller])
        db.session.commit()
        self.login_as(self.seller)

    def login_as(self, user):
        g.pop('_login_user', None)
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)

    def payload(self, radius='30'):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)
        self.assertIsNotNone(token)
        return dict(csrf_token=token.group(1), latitude='-25', longitude='-57',
                    address='Business address', delivery_radius_km=radius)

    def test_merchant_changes_10_to_30_and_buyer_visibility(self):
        self.login_as(self.buyer)
        self.check_distance(20, False)
        self.login_as(self.seller)
        response = self.client.post('/admin/business/coverage', data=self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.business.delivery_radius_km, 30)
        self.assertEqual(self.other.delivery_radius_km, 10)
        self.login_as(self.buyer)
        self.check_distance(20, True)

    def test_reject_invalid_radius(self):
        for radius in ('999', '0', '-1', '4', 'nan', '10.5', ''):
            response = self.client.post('/admin/business/coverage', data=self.payload(radius))
            self.assertEqual(response.status_code, 400, radius)
            self.assertEqual(self.business.delivery_radius_km, 10)

    def test_reject_other_business_and_roles(self):
        for key, value in [('business_id', str(self.other.id)), ('id', str(self.other.id)),
                           ('is_admin', 'false'), ('is_super_admin', 'true'), ('seller_type', 'gold')]:
            data = self.payload()
            data[key] = value
            self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 403)
        self.assertEqual(self.client.post(f'/admin/business/coverage?business_id={self.other.id}', data=self.payload()).status_code, 403)
        self.assertEqual(self.client.post(f'/admin/business/{self.other.id}/coverage', data=self.payload()).status_code, 404)
        self.assertEqual(self.business.delivery_radius_km, 10)
        self.assertEqual(self.other.delivery_radius_km, 10)
        self.assertTrue(self.seller.is_admin)
        self.assertFalse(self.seller.is_super_admin)

    def test_location_validation_and_save(self):
        data = self.payload()
        data.update(latitude='0', longitude='0')
        self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 302)
        self.assertEqual((self.business.latitude, self.business.longitude, self.business.address), (0, 0, 'Business address'))
        for key, value in [('latitude', '91'), ('longitude', '181'), ('latitude', 'nan'), ('longitude', 'inf')]:
            data = self.payload()
            data[key] = value
            self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 400)
            self.assertEqual((self.business.latitude, self.business.longitude), (0, 0))

    def test_csrf_and_buyer_cannot_update(self):
        data = self.payload()
        data.pop('csrf_token')
        self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 400)
        self.login_as(self.buyer)
        self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 302)
        self.assertEqual(self.business.delivery_radius_km, 10)

    def test_panel_and_all_allowed_radii(self):
        response = self.client.get('/admin/')
        self.assertIn('UBICACIÓN DEL NEGOCIO', response.text)
        self.assertIn('RADIO DE COBERTURA', response.text)
        self.assertIn('10.0 km', response.text)
        for radius in (1, 2, 3, 5, 10, 15, 20, 30, 50):
            self.assertEqual(self.client.post('/admin/business/coverage', data=self.payload(str(radius))).status_code, 302)
            self.assertEqual(self.business.delivery_radius_km, radius)

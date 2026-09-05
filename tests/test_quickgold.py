import re
import unittest
import test_merchant_coverage
from models import db, Business, Product


class QuickGoldTest(unittest.TestCase):
    setUp = test_merchant_coverage.MerchantCoverageTest.setUp
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as
    check_distance = test_merchant_coverage.MerchantCoverageTest.check_distance
    payload = test_merchant_coverage.MerchantCoverageTest.payload

    def admin_payload(self, seller_type):
        self.login_as(self.admin)
        response = self.client.get('/super-admin/businesses')
        self.assertEqual(response.status_code, 200)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)
        self.assertIsNotNone(token)
        return {'csrf_token': token.group(1), 'seller_type': seller_type}

    def change_type(self, seller_type):
        data = self.admin_payload(seller_type)
        return self.client.post(f'/super-admin/businesses/{self.business.id}/quickgold', data=data)

    def test_normal_quickgold_normal_preserves_coverage(self):
        self.assertFalse(self.business.is_quickgold)
        original = (self.business.latitude, self.business.longitude, self.business.address, self.business.delivery_radius_km)
        self.login_as(self.buyer)
        self.check_distance(20, False)
        self.assertEqual(self.change_type('quickgold').status_code, 302)
        self.login_as(self.buyer)
        self.check_distance(5, True)
        self.check_distance(20, True)
        self.check_distance(100, True)
        self.assertEqual(self.change_type('normal').status_code, 302)
        self.assertEqual((self.business.latitude, self.business.longitude, self.business.address, self.business.delivery_radius_km), original)
        self.login_as(self.buyer)
        self.check_distance(20, False)
        self.check_distance(5, True)

    def test_merchant_cannot_self_promote(self):
        data = self.payload()
        data['is_quickgold'] = 'true'
        self.assertEqual(self.client.post('/admin/business/coverage', data=data).status_code, 403)
        data = self.admin_payload('quickgold')
        self.login_as(self.seller)
        self.assertEqual(self.client.post(f'/super-admin/businesses/{self.business.id}/quickgold', data=data).status_code, 403)
        self.assertFalse(self.business.is_quickgold)

    def test_buyer_cannot_change_type(self):
        data = self.admin_payload('quickgold')
        self.login_as(self.buyer)
        self.assertEqual(self.client.post(f'/super-admin/businesses/{self.business.id}/quickgold', data=data).status_code, 403)
        self.assertFalse(self.business.is_quickgold)

    def test_invalid_type_csrf_extra_fields(self):
        self.assertEqual(self.change_type('invalid').status_code, 400)
        data = self.admin_payload('quickgold')
        data.pop('csrf_token')
        self.assertEqual(self.client.post(f'/super-admin/businesses/{self.business.id}/quickgold', data=data).status_code, 400)
        data = self.admin_payload('quickgold')
        data['delivery_radius_km'] = '999'
        self.assertEqual(self.client.post(f'/super-admin/businesses/{self.business.id}/quickgold', data=data).status_code, 400)
        self.assertFalse(self.business.is_quickgold)
        self.assertEqual(self.business.delivery_radius_km, 10)

    def test_multiple_quickgold_and_existing_product_filters(self):
        self.business.is_quickgold = True
        self.other.is_quickgold = True
        # Geographical data is not required to display QuickGold.
        self.other.latitude = self.other.longitude = None
        db.session.add(Product(name='Second Gold Product', business_id=self.other.id, price=100, stock=1))
        db.session.add(Product(name='Inactive Product', business_id=self.other.id, price=100, stock=1, is_active=False))
        db.session.add(Product(name='Empty Product', business_id=self.other.id, price=100, stock=0))
        db.session.commit()
        self.login_as(self.buyer)
        for url in ('/', '/products'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Coverage Product', response.text)
            self.assertIn('Second Gold Product', response.text)
            self.assertNotIn('Inactive Product', response.text)
            self.assertNotIn('Empty Product', response.text)
        self.other.is_active = False
        db.session.commit()
        self.assertNotIn('Second Gold Product', self.client.get('/products').text)

    def test_super_admin_list_displays_type_and_stored_radius(self):
        self.change_type('quickgold')
        response = self.client.get('/super-admin/businesses')
        self.assertIn('QUICKGOLD', response.text)
        self.assertIn('Sin límite geográfico', response.text)
        self.assertIn('Radio guardado: 10.0 km', response.text)
        self.assertEqual(self.client.get('/super-admin/businesses/search?q=Coverage').status_code, 200)

    def test_quickgold_keeps_merchant_radius_editing(self):
        self.change_type('quickgold')
        self.login_as(self.seller)
        self.assertEqual(self.client.post('/admin/business/coverage', data=self.payload('30')).status_code, 302)
        self.assertTrue(self.business.is_quickgold)
        self.assertEqual(self.business.delivery_radius_km, 30)
        self.change_type('normal')
        self.login_as(self.buyer)
        self.check_distance(20, True)

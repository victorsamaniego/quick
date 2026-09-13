import unittest
from models import db, Order, Product, OrderItem
import test_merchant_coverage


class AnalyticsTest(unittest.TestCase):
    setUp = test_merchant_coverage.MerchantCoverageTest.setUp
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as

    def test_empty(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.get('/super-admin/analytics').status_code, 200)

    def test_historical_null_optional_fields_and_zero_revenue(self):
        self.login_as(self.admin)
        order = Order(user_id=self.buyer.id, business_id=self.business.id,
                      status='delivered', total_amount=0,
                      shipping_address='Test', shipping_phone='000')
        db.session.add(order)
        db.session.commit()
        self.assertEqual(self.client.get('/super-admin/analytics').status_code, 200)

    def test_products_and_businesses(self):
        self.login_as(self.admin)
        for business, total in [(self.business, 100), (self.other, 700)]:
            product = Product(name='Same product', business_id=business.id, price=total, stock=20)
            order = Order(user_id=self.buyer.id, business_id=business.id, status='delivered',
                          total_amount=total, shipping_address='Test', shipping_phone='000')
            db.session.add_all([product, order])
            db.session.flush()
            db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1, price_at_purchase=total))
        db.session.commit()
        response = self.client.get('/super-admin/analytics')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Coverage Shop', response.text)
        self.assertIn('Other shop', response.text)

    def test_merchant_and_delivery_denied(self):
        self.assertEqual(self.client.get('/super-admin/analytics').status_code, 302)
        self.seller.is_delivery = True
        db.session.commit()
        self.assertEqual(self.client.get('/super-admin/analytics').status_code, 302)

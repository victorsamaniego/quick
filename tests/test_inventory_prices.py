import unittest
from unittest.mock import patch
from pathlib import Path
from flask import render_template_string
from models import db, Product, User, Order, OrderItem
import routes
import test_merchant_coverage


class InventoryPricesTest(unittest.TestCase):
    setUp = test_merchant_coverage.MerchantCoverageTest.setUp
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as

    def test_inventory_isolation_and_render(self):
        existing = Product.query.filter_by(business_id=self.business.id).one()
        existing.name, existing.stock, existing.price = 'Pilsen', 18, 8500
        db.session.add_all([
            Product(name='POD UVA', business_id=self.business.id, stock=2, price=65000),
            Product(name='Zero stock', business_id=self.business.id, stock=0, price=999),
            Product(name='Free', business_id=self.business.id, stock=4, price=0),
            Product(name='PRIVATE BUSINESS B', business_id=self.other.id, stock=999, price=999999)])
        db.session.commit()
        with patch.object(routes, 'render_template', side_effect=lambda template, **kw: {
            'count': kw['inventory']['product_count'], 'units': kw['inventory']['units'],
            'value': str(kw['inventory']['value'])}):
            response = self.client.get('/admin/inventory?business_id=' + str(self.other.id))
            self.assertEqual(response.json, {'count': 4, 'units': 24, 'value': '283000.0'})
        response = self.client.get('/admin/inventory')
        self.assertEqual(response.status_code, 200)
        self.assertIn('GS 283.000', response.text)
        self.assertIn('POD UVA', response.text)
        self.assertNotIn('PRIVATE BUSINESS B', response.text)
        self.assertIn('col-12 col-md-6', response.text)
        other_seller = User(username='seller-b', email='seller-b@test.invalid', phone='000',
                            password_hash=self.buyer.password_hash, is_admin=True, business_id=self.other.id)
        self.other.requires_subscription = False
        db.session.add(other_seller)
        db.session.commit()
        self.login_as(other_seller)
        response = self.client.get('/admin/inventory?business_id=' + str(self.business.id))
        self.assertIn('PRIVATE BUSINESS B', response.text)
        self.assertNotIn('POD UVA', response.text)
        self.assertNotIn('GS 283.000', response.text)

    def test_unauthorized(self):
        from flask import g
        g.pop('_login_user', None)
        self.assertEqual(self.app.test_client().get('/admin/inventory').status_code, 401)
        self.login_as(self.buyer)
        self.assertEqual(self.client.get('/admin/inventory').status_code, 302)
        self.login_as(self.seller)
        self.seller.business_id = None
        db.session.commit()
        self.assertEqual(self.client.get('/admin/inventory').status_code, 403)

    def test_saved_purchase_price_survives_catalog_change_in_all_order_views(self):
        product = Product.query.filter_by(business_id=self.business.id).one()
        product.price = 8500
        order = Order(user_id=self.buyer.id, business_id=self.business.id, total_amount=283000, shipping_address='Test address', shipping_phone='000')
        first = OrderItem(order=order, product=product, product_name='Pilsen', quantity=18, price_at_purchase=product.price)
        second = OrderItem(order=order, product_name='POD UVA', quantity=2, price_at_purchase=65000)
        db.session.add_all([order, first, second])
        db.session.commit()
        self.assertEqual((first.price_at_purchase, first.subtotal), (8500, 153000))
        product.price = 10000
        db.session.commit()
        db.session.expire_all()
        for item, price, subtotal in [(first, 8500, 153000), (second, 65000, 130000)]:
            self.assertEqual(item.price_at_purchase, price)
            self.assertEqual(item.subtotal, subtotal)
            self.assertEqual(item.quantity * item.price_at_purchase, subtotal)
            # Render the actual price cell expression from every OrderItem view.
            for name in ['admin/orders.html', 'admin/order_map.html', 'dashboard.html', 'delivery/order_detail.html']:
                source = (Path(routes.__file__).parent / 'templates' / name).read_text(encoding='utf-8')
                expression = next(line for line in source.splitlines() if 'format(item.price_at_purchase)' in line)
                rendered = render_template_string(expression, item=item)
                self.assertIn(format(price, ',.0f'), rendered)
                self.assertNotIn('10,000', rendered)

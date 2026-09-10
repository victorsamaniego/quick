import re
import unittest
import test_order_destination
from extensions import csrf, limiter
from models import Product


class CSRFAndRateSecurityTest(unittest.TestCase):
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def setUp(self):
        test_order_destination.OrderDestinationTest.setUp(self)
        csrf.init_app(self.app)
        limiter.init_app(self.app)
        limiter.reset()

    def test_raw_sensitive_post_requires_csrf_and_valid_token_works(self):
        data = self.checkout()
        product = Product.query.one()
        self.assertEqual(self.client.post(f'/cart/add/{product.id}').status_code, 400)
        self.assertEqual(self.client.post(f'/cart/add/{product.id}', data={'csrf_token': data['csrf_token']}).status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'][str(product.id)], 2)

    def test_json_header_required_and_valid_token_works(self):
        token = self.checkout()['csrf_token']
        payload = {'latitude': -25, 'longitude': -57}
        self.assertEqual(self.client.post('/api/update-user-location', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/api/update-user-location', json=payload, headers={'X-CSRFToken': token}).status_code, 200)

    def test_recovery_rate_limit(self):
        anonymous = self.app.test_client()
        page = anonymous.get('/recover')
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
        for _ in range(5):
            self.assertEqual(anonymous.post('/recover', data={'identifier': 'missing', 'csrf_token': token}).status_code, 200)
        self.assertEqual(anonymous.post('/recover', data={'identifier': 'missing', 'csrf_token': token}).status_code, 429)

    def test_oversized_http_upload_rejected(self):
        self.app.config['MAX_CONTENT_LENGTH'] = 1024
        self.assertEqual(self.client.post('/recover', data={'identifier': 'x' * 2048}).status_code, 413)

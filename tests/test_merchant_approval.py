import unittest
from flask import g
from models import db, User, Business
from realtime import allowed_room, socketio, register_realtime
from merchant_feature_support import FeatureFixture


class MerchantApprovalTest(FeatureFixture, unittest.TestCase):
    def decision(self, action='approve', business=None, **data):
        business = business or self.business
        data.setdefault('csrf_token', self.token())
        return self.client.post(f'/super-admin/merchant-requests/{business.id}/{action}', data=data)

    def test_customer_registration_stays_operational(self):
        self.assertEqual(self.registration('customer').status_code, 302)
        user = User.query.filter_by(username='newmerchant').one()
        self.assertFalse(user.is_admin)
        self.assertIsNone(user.business_id)
        self.assertIsNotNone(user.legal_accepted_at)
        self.assertEqual(user.legal_version, '2026-09-22')
        g.pop('_login_user', None)
        self.assertEqual(self.client.get('/dashboard').status_code, 200)

    def test_business_registration_and_real_login_pending(self):
        self.assertEqual(self.registration().status_code, 302)
        user = User.query.filter_by(username='newmerchant').one()
        self.assertIsNotNone(user.business_id)
        self.assertEqual(user.business.approval_status, 'pending')
        self.assertFalse(user.business.is_active)
        self.assertEqual(user.business.admin_user.id, user.id)
        response = self.client.post('/login?next=/admin/products', data={
            'username':user.username, 'password':self.password, 'csrf_token':self.token('/login')})
        self.assertEqual(response.status_code, 302)
        g.pop('_login_user', None)
        transition = self.client.get(response.location)
        self.assertTrue(response.location.endswith('/merchant/status'))
        self.assertEqual(transition.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], str(user.id))
        self.assertIn('Perfil en proceso', self.client.get('/merchant/status').text)

    def test_pending_all_operational_get_routes_blocked(self):
        self.pending()
        self.login_as(self.seller)
        for path in ('/admin/', '/admin/products', '/admin/orders', '/admin/inventory',
                     '/admin/cash-register', '/dashboard', '/admin/stats', '/soporte', '/activate-subscription', '/account/settings'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith('/merchant/status'))
        page = self.client.get('/merchant/status').text
        self.assertIn('Perfil en proceso', page)
        self.assertNotIn('href="/admin/', page)
        self.assertNotIn('js/main.js', page)
        for path in ('/admin/products/new', '/admin/business/coverage', '/api/update-user-location'):
            self.assertEqual(self.client.post(path, data={'csrf_token':self.token()}).status_code, 403)
        self.assertEqual(self.client.get('/api/products/search?q=ab').status_code, 403)

    def test_non_superadmin_cannot_decide_or_read(self):
        self.pending()
        for user in (self.buyer, self.seller, self.driver, None):
            self.login_as(user)
            for action in ('approve','reject'):
                self.assertIn(self.decision(action).status_code, (302, 401, 403))
                self.assertEqual(self.business.approval_status, 'pending')
            for path in ('/super-admin/merchant-requests', f'/super-admin/merchant-requests/{self.business.id}'):
                self.assertIn(self.client.get(path).status_code, (302, 401, 403))

    def test_approval_audit_and_existing_subscription_rules(self):
        self.pending()
        self.login_as(self.admin)
        before = (self.business.is_quickgold, self.business.delivery_radius_km,
                  self.business.cash_register_enabled, self.business.subscription_status,
                  self.business.commission_rate)
        self.assertEqual(self.decision().status_code, 302)
        db.session.refresh(self.business)
        self.assertEqual(self.business.approval_status, 'approved')
        self.assertTrue(self.business.is_active)
        self.assertEqual(self.business.approved_by_user_id, self.admin.id)
        self.assertIsNotNone(self.business.approved_at)
        self.assertEqual(before, (self.business.is_quickgold, self.business.delivery_radius_km,
                  self.business.cash_register_enabled, self.business.subscription_status,
                  self.business.commission_rate))
        self.login_as(self.seller)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.business.requires_subscription = True
        db.session.commit()
        self.assertIn('activate', self.client.get('/admin/').location)

    def test_rejection_preserves_records_and_blocks(self):
        self.pending()
        self.login_as(self.admin)
        self.assertEqual(self.decision('reject', rejection_reason='<script>test</script>').status_code, 302)
        db.session.refresh(self.business)
        self.assertEqual(self.business.approval_status, 'rejected')
        self.assertFalse(self.business.is_active)
        self.assertEqual(self.business.rejected_by_user_id, self.admin.id)
        self.assertIsNotNone(self.business.rejected_at)
        self.assertIsNotNone(db.session.get(User,self.seller.id))
        self.login_as(self.seller)
        self.assertEqual(self.client.get('/admin/products').status_code, 302)
        page = self.client.get('/merchant/status').text
        self.assertIn('SOLICITUD NO APROBADA', page)
        self.assertIn('&lt;script&gt;test&lt;/script&gt;', page)
        self.assertNotIn('<script>test</script>', page)

    def test_post_csrf_validation_and_repeated_decisions(self):
        self.pending()
        self.login_as(self.admin)
        for action in ('approve', 'reject'):
            path = f'/super-admin/merchant-requests/{self.business.id}/{action}'
            self.assertEqual(self.client.get(path).status_code, 405)
            self.assertEqual(self.client.post(path).status_code, 400)
        self.assertEqual(self.decision('reject', rejection_reason='a'*301).status_code, 400)
        self.assertEqual(self.business.approval_status, 'pending')
        self.assertEqual(self.client.post('/super-admin/merchant-requests/999999/approve', data={'csrf_token':self.token()}).status_code,404)
        self.assertEqual(self.decision().status_code,302)
        self.assertEqual(self.decision('reject').status_code,409)
        self.assertEqual(self.business.approval_status,'approved')

    def test_count_and_detail_follow_database(self):
        self.pending()
        self.login_as(self.admin)
        self.assertIn('1 pendientes de revisión', self.client.get('/super-admin/').text)
        detail = self.client.get(f'/super-admin/merchant-requests/{self.business.id}').text
        for value in (self.seller.username, self.seller.email, self.seller.phone):
            self.assertIn(value, detail)
        self.assertEqual(self.client.get('/super-admin/merchant-requests?status=bad').status_code,400)
        self.assertEqual(self.decision().status_code,302)
        self.assertIn('0 pendientes de revisión', self.client.get('/super-admin/').text)
        self.pending()
        self.assertEqual(self.decision('reject').status_code,302)
        self.assertIn('0 pendientes de revisión', self.client.get('/super-admin/').text)

    def test_existing_business_default_and_pending_logout(self):
        self.assertEqual(self.other.approval_status,'approved')
        self.login_as(self.seller)
        self.assertEqual(self.client.get('/admin/').status_code,200)
        self.pending()
        self.assertEqual(self.client.post('/logout', data={'csrf_token':self.token()}).status_code,302)
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id',session)

    def test_pending_and_rejected_cannot_connect_socket_or_join_rooms(self):
        socketio.init_app(self.app, async_mode='threading')
        register_realtime(self.app)
        self.login_as(self.seller)
        for status in ('pending','rejected'):
            self.business.approval_status = status
            db.session.commit()
            self.assertFalse(allowed_room(self.seller, f'business_{self.business.id}'))
            self.assertFalse(allowed_room(self.seller, f'user_{self.seller.id}'))
            client = socketio.test_client(self.app, flask_test_client=self.client)
            self.assertFalse(client.is_connected())

    def test_waiting_page_is_exclusive_and_not_cached(self):
        self.pending()
        self.login_as(self.seller)
        response = self.client.get('/merchant/status')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['Cache-Control'])
        for text in ('Perfil en proceso', 'pendiente de aprobación', 'Super Admin',
                     'No necesitás volver a registrarte.', 'Cerrar sesión'):
            self.assertIn(text, response.text)
        for text in ('<nav', 'js/main.js', 'socket.io', 'web_push.js', 'notifications.js'):
            self.assertNotIn(text, response.text)
        self.assertTrue(self.client.get('/login').location.endswith('/merchant/status'))
        self.assertEqual(self.client.post('/logout').status_code, 400)

    def test_existing_session_leaves_waiting_page_after_approval(self):
        self.pending()
        self.login_as(self.seller)
        merchant_client = self.client
        self.assertEqual(merchant_client.get('/merchant/status').status_code, 200)
        self.client = self.app.test_client()
        self.login_as(self.admin)
        self.assertEqual(self.decision().status_code, 302)
        g.pop('_login_user', None)
        response = merchant_client.get('/merchant/status', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, '/admin/')
        self.assertNotIn('Perfil en proceso', response.text)

    def test_requests_identify_merchant_not_placeholder_business(self):
        self.pending()
        self.business.name = 'Pendiente - Usuario'
        db.session.commit()
        self.login_as(self.admin)
        for path in ('/super-admin/merchant-requests',
                     f'/super-admin/merchant-requests/{self.business.id}'):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn('COMERCIANTE', page.text)
            self.assertIn('Tipo de solicitud', page.text)
            self.assertNotIn('Pendiente - Usuario', page.text)
            for value in (self.seller.username, self.seller.email, self.seller.phone):
                self.assertIn(value, page.text)

    def test_socket_budget_rechecks_existing_connection(self):
        from socket_security import socket_budget
        self.login_as(self.seller)
        calls = []
        @socket_budget('waiting-test', 10)
        def operation():
            calls.append(True)
            return {'success': True}
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(self.seller)
            for status in ('pending', 'rejected'):
                self.business.approval_status = status
                db.session.commit()
                self.assertEqual(operation(), {'success': False})
            self.assertEqual(calls, [])

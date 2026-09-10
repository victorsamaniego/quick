"""REV3 continuation: isolated fixtures, no production imports or credentials."""
import json
import os
import re
import secrets
import unittest
from unittest.mock import patch
from flask import Flask
import test_order_destination
import test_realtime
from extensions import csrf
from models import db, User, Product, Order, SecurityQuestion
from runtime_security import configure_runtime_security


class RuntimeSecurityTest(unittest.TestCase):
    def test_production_fails_closed_before_extensions(self):
        for value in (None, 'dev', 'x' * 64):
            app = Flask(__name__); app.secret_key = value
            with patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=True):
                with self.assertRaises(RuntimeError):
                    configure_runtime_security(app)
        for flag in ('DEBUG', 'TESTING'):
            app = Flask(__name__); app.secret_key = secrets.token_urlsafe(40); app.config[flag] = True
            with patch.dict(os.environ, {'FLASK_ENV': 'production'}, clear=True):
                with self.assertRaises(RuntimeError):
                    configure_runtime_security(app)

    def test_production_cookies_and_local_http(self):
        for env, secure in [('production', True), ('development', False), ('testing', False)]:
            app = Flask(__name__); app.secret_key = secrets.token_urlsafe(40)
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
            with patch.dict(os.environ, {'FLASK_ENV': env}, clear=True):
                configure_runtime_security(app)
            self.assertEqual(app.config['SESSION_COOKIE_SECURE'], secure)
            self.assertEqual(app.config['REMEMBER_COOKIE_SECURE'], secure)
            self.assertTrue(app.config['REMEMBER_COOKIE_HTTPONLY'])
            self.assertEqual(app.config['REMEMBER_COOKIE_DURATION'].days, 7)

    def test_local_key_is_ephemeral(self):
        first, second = Flask('first'), Flask('second')
        with patch.dict(os.environ, {}, clear=True):
            configure_runtime_security(first); configure_runtime_security(second)
        self.assertTrue(first.secret_key and first.secret_key != second.secret_key)

    def test_configured_host_rejects_poisoning(self):
        app = Flask(__name__)
        with patch.dict(os.environ, {'TRUSTED_HOSTS': 'quickgo.test', 'PUBLIC_BASE_URL': 'https://quickgo.test'}, clear=True):
            configure_runtime_security(app)
        app.add_url_rule('/', view_func=lambda: app.config['PUBLIC_BASE_URL'])
        self.assertEqual(app.test_client().get('/', headers={'Host': 'attacker.test'}).status_code, 400)
        response = app.test_client().get('/', headers={'Host': 'quickgo.test', 'X-Forwarded-Host': 'attacker.test'})
        self.assertEqual(response.text, 'https://quickgo.test')


class AdminContinuationSecurityTest(unittest.TestCase):
    setUp = test_order_destination.OrderDestinationTest.setUp
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def test_coverage_opt_in_rejects_direct_url_and_checkout_without_stock_change(self):
        self.app.config['SECURITY_ENFORCE_COVERAGE'] = True
        data = self.checkout('0', '0')
        product = Product.query.one()
        self.assertEqual(self.client.get(f'/product/{product.id}').status_code, 400)
        self.assertEqual(self.client.post(f'/cart/add/{product.id}').status_code, 400)
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 400)
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(product.stock, 3)

    def test_coverage_opt_in_preserves_quickgold_and_blocks_inactive(self):
        self.app.config['SECURITY_ENFORCE_COVERAGE'] = True
        self.business.is_quickgold = True; db.session.commit()
        data = self.checkout('0', '0')
        product = Product.query.one()
        self.assertEqual(self.client.get(f'/product/{product.id}').status_code, 200)
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        self.assertEqual(Order.query.count(), 1)
        self.business.is_active = False; db.session.commit()
        self.assertEqual(self.client.get(f'/product/{product.id}').status_code, 400)

    def test_coverage_opt_in_allows_inside_radius(self):
        self.app.config['SECURITY_ENFORCE_COVERAGE'] = True
        data = self.checkout('-25', '-57')
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        self.assertEqual(Order.query.count(), 1)

    def test_recovery_cannot_reuse_verification_for_another_identity(self):
        question = SecurityQuestion(question='Pregunta de prueba')
        db.session.add(question); db.session.flush()
        self.buyer.security_question_id = question.id
        self.buyer.set_security_answer(secrets.token_urlsafe(32)); db.session.commit()
        anonymous = self.app.test_client()
        with anonymous.session_transaction() as session:
            session['recover_user_id'] = self.admin.id
            session['security_verified'] = True
            session['final_verified'] = True
        from flask import g
        g.pop('_login_user', None)
        self.assertEqual(anonymous.post('/recover', data={'identifier': self.buyer.email}).status_code, 302)
        with anonymous.session_transaction() as session:
            self.assertEqual(session['recover_user_id'], self.buyer.id)
            self.assertNotIn('security_verified', session)
            self.assertNotIn('final_verified', session)
        self.assertEqual(anonymous.get('/recover/reset-password').status_code, 302)

    def test_text_limits_reject_large_payloads(self):
        self.login_as(self.admin)
        self.assertEqual(self.client.post('/super-admin/notifications/new', data={
            'title': 'x' * 201, 'message': 'normal'}).status_code, 400)

    def test_last_active_superadmin_cannot_be_demoted_or_disabled(self):
        self.login_as(self.admin)
        for extra in ({'is_active': 'on'}, {'is_super_admin': 'on'}):
            response = self.client.post(f'/super-admin/users/{self.admin.id}/edit', data={
                'email': self.admin.email, 'phone': self.admin.phone, **extra})
            self.assertEqual(response.status_code, 409)
            self.assertTrue(self.admin.is_super_admin and self.admin.is_active)

    def test_incompatible_roles_rejected_and_seller_cannot_promote(self):
        self.login_as(self.admin)
        response = self.client.post(f'/super-admin/users/{self.buyer.id}/edit', data={
            'email': self.buyer.email, 'phone': self.buyer.phone, 'is_active': 'on',
            'is_super_admin': 'on', 'is_delivery': 'on'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.buyer.is_super_admin or self.buyer.is_delivery)
        self.login_as(self.seller)
        self.assertEqual(self.client.post(f'/super-admin/users/{self.seller.id}/edit',
                         data={'is_super_admin': 'on'}).status_code, 302)
        self.assertFalse(self.seller.is_super_admin)

    def test_last_superadmin_delete_preserves_user(self):
        self.login_as(self.admin)
        count = User.query.count()
        self.assertEqual(self.client.post(f'/super-admin/users/{self.admin.id}/delete').status_code, 302)
        self.assertEqual(User.query.count(), count)

    def test_reset_secret_not_in_cookie_or_flash(self):
        self.login_as(self.admin)
        temporary = secrets.token_urlsafe(32)
        with patch('routes.secrets.token_urlsafe', return_value=temporary):
            response = self.client.post(f'/super-admin/users/{self.buyer.id}/reset-password')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(temporary in response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        with self.client.session_transaction() as session:
            self.assertTrue(temporary not in json.dumps(dict(session)))
        self.assertTrue(self.buyer.check_password(temporary))

    def test_activation_secret_not_in_cookie_or_flash(self):
        self.business.requires_subscription = True
        db.session.commit(); self.login_as(self.admin)
        response = self.client.post(f'/super-admin/businesses/{self.business.id}/generate-code')
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertTrue(self.business.activation_code not in json.dumps(dict(session)))

    def test_logout_get_does_not_change_auth_and_post_requires_csrf(self):
        csrf.init_app(self.app)
        self.login_as(self.buyer)
        page = self.client.get('/logout')
        self.assertEqual(page.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], str(self.buyer.id))
        self.assertEqual(self.client.post('/logout').status_code, 400)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
        self.assertEqual(self.client.post('/logout', data={'csrf_token': token}).status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)


class SocketContinuationSecurityTest(unittest.TestCase):
    setUp = test_realtime.RealtimeTest.setUp
    tearDown = test_realtime.RealtimeTest.tearDown
    connect = test_realtime.RealtimeTest.connect
    join = test_realtime.RealtimeTest.join
    login_as = test_realtime.RealtimeTest.login_as

    def test_join_flood_shared_across_connections_and_recovers(self):
        first, second = self.connect(self.buyer), self.connect(self.buyer)
        room = f'user_{self.buyer.id}'
        with patch('socket_security.monotonic', return_value=100):
            for _ in range(120):
                self.assertTrue(self.join(first, room)['success'])
            self.assertFalse(self.join(second, room)['success'])
        with patch('socket_security.monotonic', return_value=161):
            self.assertTrue(self.join(second, room)['success'])

    def test_huge_room_and_invalid_payload_do_not_raise(self):
        sock = self.connect(self.buyer)
        self.assertFalse(self.join(sock, 'user_' + '9' * 5000)['success'])
        for value in (None, [], {'room': {}}, {'room': 4}):
            self.assertFalse(sock.emit('join', value, callback=True)['success'])

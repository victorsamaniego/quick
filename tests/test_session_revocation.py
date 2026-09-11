import re
import secrets
import unittest
from flask import g
from flask_login import login_required
import test_order_destination
import test_realtime
from models import db
from auth_identity import load_security_user
from auth_tokens import issue_reset_token, consume_reset_token
from extensions import limiter
from realtime import socketio, publish


class SessionRevocationTest(unittest.TestCase):
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as

    def setUp(self):
        test_order_destination.OrderDestinationTest.setUp(self)
        self.app.config['SECURITY_SESSION_REVOCATION'] = True
        self.app.login_manager.user_loader(load_security_user)
        self.app.login_manager.login_view = 'main.login'
        limiter.init_app(self.app); limiter.reset()
        self.password = secrets.token_urlsafe(32) + 'aA1!'
        self.buyer.set_password(self.password); self.admin.set_password(self.password); db.session.commit()
        self.app.add_url_rule('/identity-test', view_func=login_required(lambda: 'ok'))

    def login(self, user, password=None):
        limiter.reset()
        client = self.app.test_client(); g.pop('_login_user', None)
        # This fixture retains an app context; separate browser sessions need
        # separate Flask-WTF request caches as they do in normal requests.
        g.pop('csrf_token', None)
        page = client.get('/login')
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
        g.pop('_login_user', None)
        self.assertEqual(client.post('/login', data={'username':user.username,
            'password':password or self.password,'remember_me':'y','csrf_token':token}).status_code, 302)
        return client

    def access(self, client):
        g.pop('_login_user', None)
        return client.get('/identity-test').status_code

    def test_change_password_revokes_two_sessions_and_remember_cookie(self):
        first, second = self.login(self.buyer), self.login(self.buyer)
        cookie = first.get_cookie('remember_token').value
        remembered = self.app.test_client(); remembered.set_cookie('remember_token', cookie)
        self.assertEqual(self.access(remembered), 200)
        new_password = secrets.token_urlsafe(32) + 'aA1!'
        self.buyer.set_password(new_password); db.session.commit()
        for client in (first, second, remembered): self.assertEqual(self.access(client), 302)
        replay = self.app.test_client(); replay.set_cookie('remember_token', cookie)
        self.assertEqual(self.access(replay), 302)
        self.assertEqual(self.access(self.login(self.buyer, new_password)), 200)

    def test_token_reset_revokes_session(self):
        client = self.login(self.buyer)
        raw = issue_reset_token(self.buyer.id)
        self.assertTrue(consume_reset_token(raw, secrets.token_urlsafe(32)+'aA1!'))
        self.assertEqual(self.access(client), 302)

    def test_admin_reset_revokes_session(self):
        buyer = self.login(self.buyer)
        admin = self.login(self.admin); g.pop('_login_user', None)
        self.assertEqual(admin.post(f'/super-admin/users/{self.buyer.id}/reset-password').status_code, 200)
        self.assertEqual(self.access(buyer), 302)

    def test_activation_rejects_legacy_and_malformed_ids(self):
        for identity in (str(self.buyer.id), 'v1.invalid', '9'*1000, 'v1.'+'9'*19+'.'+'a'*64):
            self.assertIsNone(load_security_user(identity))


class SocketRevocationTest(unittest.TestCase):
    setUp = test_realtime.RealtimeTest.setUp
    tearDown = test_realtime.RealtimeTest.tearDown
    login_as = test_realtime.RealtimeTest.login_as

    def test_connected_socket_loses_rooms_and_cannot_rejoin_after_reset(self):
        self.app.config['SECURITY_SESSION_REVOCATION'] = True
        self.app.login_manager.user_loader(load_security_user)
        client = self.app.test_client()
        with client.session_transaction() as session: session['_user_id'] = self.buyer.get_id()
        g.pop('_login_user', None)
        sock = socketio.test_client(self.app, flask_test_client=client)
        self.assertTrue(sock.is_connected()); self.sockets.append(sock); sock.get_received()
        self.buyer.set_password(secrets.token_urlsafe(32)); db.session.commit()
        publish('private-probe', {'message':'test'}, [f'user_{self.buyer.id}'])
        self.assertEqual(sock.get_received(), [])
        g.pop('_login_user', None)
        self.assertFalse(sock.emit('join', {'room':f'user_{self.buyer.id}'}, callback=True)['success'])
        g.pop('_login_user', None)
        reconnect = socketio.test_client(self.app, flask_test_client=client)
        self.assertFalse(reconnect.is_connected())

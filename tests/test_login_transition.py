import re
import secrets
import unittest
from html import unescape
from urllib.parse import urlencode
from flask import g
from models import db
from extensions import limiter
import test_themes


class LoginTransitionTest(unittest.TestCase):
    def tearDown(self):
        limiter.reset()
        test_themes.ThemeSettingsTest.tearDown(self)

    def setUp(self):
        test_themes.ThemeSettingsTest.setUp(self)
        limiter.init_app(self.app)
        limiter.reset()
        self.password = secrets.token_urlsafe(24)
        self.buyer.set_password(self.password)
        for user in (self.seller, self.driver, self.admin):
            user.password_hash = self.buyer.password_hash
        db.session.commit()
        self.fresh_client()

    login_as = test_themes.ThemeSettingsTest.login_as

    def fresh_client(self):
        g.pop('_login_user', None)
        g.pop('csrf_token', None)
        self.client = self.app.test_client()

    def token(self):
        g.pop('csrf_token', None)
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', self.client.get('/login').text).group(1)

    def login(self, user=None, next_path=None, password=None):
        limiter.reset()
        user = user or self.buyer
        path = '/login' + ('?' + urlencode({'next':next_path}) if next_path else '')
        return self.client.post(path, data={'username':user.email, 'password':password or self.password,
                                           'remember_me':'y', 'csrf_token':self.token()})

    def target(self, response):
        self.assertEqual(response.status_code, 200)
        return unescape(re.search(r'id="transition-continue" href="([^"]+)"', response.text).group(1))

    def test_bad_credentials_and_inactive_never_transition(self):
        response = self.login(password='incorrect-password')
        self.assertEqual(response.status_code,200)
        self.assertIn('incorrectos',response.text)
        self.assertNotIn('login_transition.js',response.text)
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id',session)
            self.assertNotIn('post_login_transition',session)
        self.buyer.is_active=False
        db.session.commit()
        response=self.login()
        self.assertTrue(response.location.endswith('/login'))
        with self.client.session_transaction() as session:
            self.assertNotIn('post_login_transition',session)

    def test_success_roles_defaults_and_remember_policy(self):
        for user,destination in ((self.buyer,'/dashboard'),(self.seller,'/admin/'),
                                 (self.driver,'/delivery/dashboard'),(self.admin,'/super-admin/')):
            self.fresh_client()
            response=self.login(user)
            self.assertEqual(response.status_code,302)
            self.assertTrue(response.location.endswith('/login/transition'))
            self.assertEqual(bool(self.client.get_cookie('remember_token')),user==self.buyer)
            page=self.client.get(response.location)
            self.assertEqual(self.target(page),destination)
            self.assertIn('no-store',page.headers['Cache-Control'])
            self.assertEqual(page.headers['Referrer-Policy'],'no-referrer')
            for absent in ('<nav','<footer','<form','socket.io','notifications.js'):
                self.assertNotIn(absent,page.text)

    def test_internal_next_and_same_origin_are_preserved(self):
        for next_path,expected in (('/product/1','/product/1'),('/cart','/cart'),
                                   ('/account/settings?tab=appearance&from=login#palette','/account/settings?tab=appearance&from=login#palette'),
                                   ('http://localhost/dashboard','/dashboard')):
            self.fresh_client()
            self.login(next_path=next_path)
            self.assertEqual(self.target(self.client.get('/login/transition')),expected)

    def test_external_and_manipulated_next_never_used(self):
        for value in ('https://evil.example','//evil.example','javascript:alert(1)',
                      '/%2fevil.example','/\\evil.example','/ok%0d%0aLocation:evil',
                      'https://localhost.evil.example','/login/transition',
                      'http://localhost//evil.example','http://localhost/%2fevil.example'):
            self.fresh_client()
            self.login(next_path=value)
            self.assertEqual(self.target(self.client.get('/login/transition')),'/dashboard')

    def test_transition_authentication_one_use_and_ignored_query(self):
        self.assertIn(self.client.get('/login/transition').status_code,(302,401))
        self.login(next_path='/account/settings')
        page=self.client.get('/login/transition?next=https://evil.example&user_id=999')
        self.assertEqual(self.target(page),'/account/settings')
        with self.client.session_transaction() as session:
            self.assertNotIn('post_login_transition',session)
        replay=self.client.get('/login/transition')
        self.assertEqual(replay.status_code,302)
        self.assertTrue(replay.location.endswith('/dashboard'))

    def test_stale_other_user_and_invalid_session_target(self):
        self.login()
        with self.client.session_transaction() as session:
            session['post_login_transition']={'user_id':self.seller.id,'target':'/admin/'}
        response=self.client.get('/login/transition')
        self.assertTrue(response.location.endswith('/dashboard'))
        with self.client.session_transaction() as session:
            session['post_login_transition']={'user_id':self.buyer.id,'target':'//evil.example'}
        self.assertEqual(self.target(self.client.get('/login/transition')),'/dashboard')

    def test_logout_clears_pending_and_login_requires_csrf(self):
        self.assertEqual(self.client.post('/login',data={'username':self.buyer.username,'password':self.password}).status_code,400)
        self.login()
        with self.client.session_transaction() as session:
            self.assertIn('post_login_transition',session)
        g.pop('csrf_token',None)
        token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',self.client.get('/logout').text).group(1)
        self.client.post('/logout',data={'csrf_token':token})
        with self.client.session_transaction() as session:
            self.assertNotIn('post_login_transition',session)
            self.assertNotIn('_user_id',session)


if __name__ == '__main__':
    unittest.main()

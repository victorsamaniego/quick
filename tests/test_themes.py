import re
import secrets
import unittest
from pathlib import Path
from flask import g
from jinja2 import FileSystemLoader
from werkzeug.datastructures import MultiDict
import test_merchant_coverage
from extensions import csrf
from models import db, User
from themes import THEMES, normalize_theme


class ThemeSettingsTest(unittest.TestCase):
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as

    def setUp(self):
        test_merchant_coverage.MerchantCoverageTest.setUp(self)
        self.app.jinja_loader = FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates'))
        csrf.init_app(self.app)
        self.driver = User(username='theme-driver', email='driver@example.test', phone='000000000',
                           password_hash=self.buyer.password_hash, is_delivery=True)
        self.admin.is_admin = True  # The failing Super Admin configuration.
        db.session.add(self.driver)
        db.session.commit()

    def token(self, path='/account/settings'):
        g.pop('csrf_token', None)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)

    def test_all_roles_settings_and_superadmin_menu(self):
        for user in (self.buyer, self.seller, self.driver, self.admin):
            self.login_as(user)
            page = self.client.get('/account/settings')
            self.assertEqual(page.status_code, 200)
            self.assertIn('qg-internal theme-gold-classic', page.text)
            self.assertIn('href="/account/settings"', page.text)
            self.assertIn('Guardar apariencia', page.text)

    def test_exact_whitelist_and_ownership(self):
        self.login_as(self.buyer)
        token = self.token()
        for data in ({'theme':'arbitrary'}, {'theme':'gold'}, {'theme':'dark-gold','user_id':self.seller.id},
                     {'theme':'sand','is_super_admin':'true'}, {},
                     MultiDict([('theme','sand'),('theme','black-gold')])):
            data = MultiDict(data)
            data.add('csrf_token', token)
            self.assertEqual(self.client.post('/account/settings', data=data).status_code, 400)
        self.assertEqual(self.client.post('/account/settings?user_id=1', data={'theme':'sand','csrf_token':token}).status_code,400)
        self.assertEqual(self.buyer.theme_color, 'gold')
        self.assertEqual(self.seller.theme_color, 'gold')

    def test_csrf_and_anonymous(self):
        self.assertEqual(self.client.post('/account/settings',data={'theme':'sand'}).status_code,400)
        g.pop('_login_user',None)
        anonymous=self.app.test_client()
        self.assertIn(anonymous.get('/account/settings').status_code,(302,401))
        self.assertEqual(self.seller.theme_color,'gold')

    def test_each_palette_saved_and_applied_for_each_role(self):
        for user in (self.buyer,self.seller,self.driver,self.admin):
            self.login_as(user)
            for theme in THEMES:
                response=self.client.post('/account/settings',data={'theme':theme,'csrf_token':self.token()},follow_redirects=True)
                self.assertEqual(response.status_code,200)
                db.session.refresh(user)
                self.assertEqual(user.theme_color,theme)
                self.assertIn('qg-internal theme-'+theme,response.text)

    def test_persists_after_real_login_and_safe_next(self):
        password=secrets.token_urlsafe(24)
        self.buyer.set_password(password)
        db.session.commit()
        self.login_as(self.buyer)
        self.client.post('/account/settings',data={'theme':'black-gold','csrf_token':self.token()})
        self.client=self.app.test_client()
        g.pop('_login_user',None)
        response=self.client.post('/login?next=/account/settings',data={'username':self.buyer.username,'password':password,'csrf_token':self.token('/login')})
        self.assertEqual(response.status_code,302,response.text)
        self.assertTrue(response.location.endswith('/account/settings'))
        g.pop('_login_user',None)
        self.assertIn('qg-internal theme-black-gold',self.client.get('/account/settings').text)

    def test_default_legacy_and_public_isolation(self):
        for value in (None,'gold','blue','<bad>'):
            self.assertEqual(normalize_theme(value),'gold-classic')
        self.assertEqual(normalize_theme('oscuro'),'dark-gold')
        self.login_as(self.buyer)
        self.buyer.theme_color='black-gold'
        db.session.commit()
        self.assertNotIn('qg-internal',self.client.get('/products').text)
        g.pop('_login_user',None)
        self.assertEqual(self.app.test_client().get('/products').status_code,200)

    def test_login_contract_and_motion(self):
        g.pop('_login_user',None)
        self.client=self.app.test_client()
        page=self.client.get('/login?next=https://evil.example')
        self.assertEqual(page.status_code,200)
        for text in ('csrf_token','remember_me','/recover','login-quick','login-go','autocomplete="current-password"'):
            self.assertIn(text,page.text)
        self.assertEqual(self.client.post('/login',data={'username':'x','password':'x'}).status_code,400)
        css=(Path(__file__).resolve().parents[1]/'static/css/login.css').read_text()
        self.assertIn('prefers-reduced-motion:reduce',css)
        self.assertIn('animation:none',css)


if __name__ == '__main__':
    unittest.main()

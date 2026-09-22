import unittest
from models import User, Business
from merchant_feature_support import FeatureFixture


class LegalPagesTest(FeatureFixture, unittest.TestCase):
    def test_public_pages_and_footer(self):
        self.login_as(None)
        for path, title in (('/privacy','Política de Privacidad de QuickGo'),('/terms','Términos y Condiciones de QuickGo')):
            page = self.client.get(path)
            self.assertEqual(page.status_code,200)
            self.assertIn(title,page.text)
            self.assertIn('href="/privacy"',page.text)
            self.assertIn('href="/terms"',page.text)
        page = self.client.get('/register').text
        checkbox = page.split('id="accept_legal"')[1].split('>')[0]
        self.assertNotIn('checked',checkbox)

    def test_no_consent_creates_neither_user_nor_business(self):
        users, businesses = User.query.count(), Business.query.count()
        self.assertEqual(self.registration(accept=False).status_code,200)
        self.assertEqual(User.query.count(),users)
        self.assertEqual(Business.query.count(),businesses)

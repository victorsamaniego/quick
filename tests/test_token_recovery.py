import hashlib
import json
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flask import g
import test_order_destination
from models import db, User
from auth_tokens import PasswordResetToken, issue_reset_token, consume_reset_token, reset_link, GENERIC_RECOVERY_MESSAGE
from extensions import csrf, limiter


class TokenRecoveryTest(unittest.TestCase):
    tearDown = test_order_destination.OrderDestinationTest.tearDown
    login_as = test_order_destination.OrderDestinationTest.login_as

    def setUp(self):
        test_order_destination.OrderDestinationTest.setUp(self)
        limiter.init_app(self.app)
        limiter.reset()
        self.app.config.update(SECURITY_TOKEN_RECOVERY=True, PUBLIC_BASE_URL='https://quickgo.test')
        self.jobs, self.mail = [], []
        self.app.config['RESET_MAIL_DISPATCH'] = self.jobs.append
        self.app.config['RESET_MAIL_SENDER'] = lambda recipient, link: self.mail.append((recipient, link))

    def password(self):
        return secrets.token_urlsafe(32) + 'aA1!'

    def test_token_hash_only_expiration_and_single_use(self):
        raw = issue_reset_token(self.buyer.id)
        token = PasswordResetToken.query.one()
        self.assertEqual(token.token_hash, hashlib.sha256(raw.encode()).hexdigest())
        self.assertTrue(raw not in repr(token) and raw not in json.dumps(token.__dict__, default=str))
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.session.commit()
        self.assertFalse(consume_reset_token(raw, self.password()))
        token.expires_at = datetime.now(timezone.utc) + timedelta(minutes=1); db.session.commit()
        password = self.password()
        self.assertTrue(consume_reset_token(raw, password))
        self.assertFalse(consume_reset_token(raw, self.password()))
        self.assertTrue(self.buyer.check_password(password))

    def test_commit_failure_does_not_consume_token_or_change_password(self):
        raw = issue_reset_token(self.buyer.id)
        previous = self.buyer.password_hash
        with patch.object(db.session, 'commit', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError): consume_reset_token(raw, self.password())
        self.assertEqual(self.buyer.password_hash, previous)
        self.assertIsNone(PasswordResetToken.query.one().used_at)

    def test_password_change_and_reissue_invalidate_previous_tokens(self):
        raw = issue_reset_token(self.buyer.id)
        self.assertIsNone(issue_reset_token(self.buyer.id))
        PasswordResetToken.query.one().created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.session.commit()
        newer = issue_reset_token(self.buyer.id)
        self.assertFalse(consume_reset_token(raw, self.password()))
        self.buyer.set_password(self.password()); db.session.commit()
        self.assertFalse(consume_reset_token(newer, self.password()))

    def test_generic_response_enqueues_unknown_and_known_without_inline_mail(self):
        client = self.app.test_client(); g.pop('_login_user', None)
        for identifier in (self.buyer.email, 'missing@example.test'):
            response = client.post('/recover', data={'identifier': identifier})
            self.assertEqual(response.status_code, 200)
            with client.session_transaction() as session:
                self.assertTrue(any(message == GENERIC_RECOVERY_MESSAGE for _, message in session['_flashes']))
                self.assertNotIn('recover_user_id', session)
        self.assertEqual(len(self.jobs), 2)
        self.assertEqual(self.mail, [])
        # Both jobs run only on isolated SQLite; adapter records mail without sending.
        for job in self.jobs: job()
        self.assertEqual(len(self.mail), 1)
        self.assertTrue(self.mail[0][1].startswith('https://quickgo.test/recover/token#'))

    def test_legacy_questions_cannot_bypass_token_mode(self):
        client = self.app.test_client(); g.pop('_login_user', None)
        previous = self.buyer.password_hash
        with client.session_transaction() as session:
            session.update(recover_user_id=self.buyer.id, security_verified=True, final_verified=True)
        for path in ('/recover/answer', '/recover/select-answer', '/recover/reset-password'):
            self.assertEqual(client.post(path, data={'new_password':self.password()}).status_code, 302)
        self.assertEqual(self.buyer.password_hash, previous)

    def test_host_does_not_control_reset_origin(self):
        with self.app.test_request_context('/', headers={'Host':'attacker.test','X-Forwarded-Host':'attacker.test'}):
            self.assertTrue(reset_link(secrets.token_urlsafe(32)).startswith('https://quickgo.test/'))

    def test_admin_reset_queues_token_without_changing_password_immediately(self):
        previous = self.buyer.password_hash
        self.login_as(self.admin)
        response = self.client.post(f'/super-admin/users/{self.buyer.id}/reset-password')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.buyer.password_hash, previous)
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.mail, [])
        self.jobs[0]()
        self.assertEqual(len(self.mail), 1)
        self.assertTrue(consume_reset_token(self.mail[0][1].split('#')[1], self.password()))

    def test_token_http_csrf_success_and_no_cookie_secret(self):
        import re
        csrf.init_app(self.app)
        raw = issue_reset_token(self.buyer.id)
        client = self.app.test_client(); g.pop('_login_user', None)
        page = client.get('/recover/token')
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
        password = self.password()
        data = dict(reset_token=raw, new_password=password, confirm_password=password)
        self.assertEqual(client.post('/recover/token', data=data).status_code, 400)
        self.assertEqual(client.post('/recover/token', data={**data,'csrf_token':token}).status_code, 302)
        with client.session_transaction() as session:
            self.assertTrue(raw not in json.dumps(dict(session)) and password not in json.dumps(dict(session)))
        self.assertTrue(self.buyer.check_password(password))

    def test_invalid_tokens_and_rate_limit(self):
        limiter.init_app(self.app); limiter.reset()
        client = self.app.test_client(); g.pop('_login_user', None)
        password = self.password()
        for _ in range(5):
            self.assertEqual(client.post('/recover/token', data={'reset_token':'invalid',
                'new_password':password,'confirm_password':password}).status_code, 400)
        self.assertEqual(client.post('/recover/token', data={}).status_code, 429)

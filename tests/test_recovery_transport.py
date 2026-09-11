import os
import secrets
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask
from auth_tokens import smtp_send
from runtime_security import configure_runtime_security


class RecoveryTransportTest(unittest.TestCase):
    def test_smtp_tls_precedes_authentication_and_no_plaintext_fallback(self):
        app = Flask(__name__)
        app.config.update(RESET_SMTP_HOST='smtp.example.test', RESET_SMTP_PORT=587,
            RESET_MAIL_FROM='no-reply@example.test', RESET_SMTP_USERNAME='synthetic',
            RESET_SMTP_PASSWORD=secrets.token_urlsafe(32))
        with app.app_context(), patch('auth_tokens.smtplib.SMTP') as smtp, patch('auth_tokens.smtplib.SMTP_SSL') as implicit:
            client = smtp.return_value.__enter__.return_value
            smtp_send('buyer@example.test', 'https://quickgo.test/recover/token#'+secrets.token_urlsafe(32))
            self.assertEqual([call[0] for call in client.method_calls], ['starttls','login','send_message'])
            implicit.assert_not_called()
            client.reset_mock(); client.starttls.side_effect = RuntimeError('synthetic failure')
            with self.assertRaises(RuntimeError): smtp_send('buyer@example.test', 'https://quickgo.test/')
            client.login.assert_not_called(); client.send_message.assert_not_called()

    def test_smtp_implicit_tls_uses_validated_context(self):
        app = Flask(__name__)
        app.config.update(RESET_SMTP_HOST='smtp.example.test', RESET_SMTP_PORT=465,
            RESET_MAIL_FROM='no-reply@example.test', RESET_SMTP_USERNAME='synthetic',
            RESET_SMTP_PASSWORD=secrets.token_urlsafe(32))
        with app.app_context(), patch('auth_tokens.smtplib.SMTP_SSL') as smtp, patch('auth_tokens.smtplib.SMTP') as plain:
            smtp_send('buyer@example.test', 'https://quickgo.test/')
            context = smtp.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, __import__('ssl').CERT_REQUIRED)
            plain.assert_not_called()

    def test_recovery_cannot_activate_without_revocation_origin_and_transport(self):
        required = dict(FLASK_ENV='testing', SECURITY_TOKEN_RECOVERY='true', SECURITY_SESSION_REVOCATION='true',
            PUBLIC_BASE_URL='https://quickgo.test', RESET_SMTP_HOST='smtp.example.test',
            RESET_SMTP_USERNAME='synthetic', RESET_SMTP_PASSWORD=secrets.token_urlsafe(32), RESET_MAIL_FROM='no-reply@example.test')
        for missing in ('SECURITY_SESSION_REVOCATION','PUBLIC_BASE_URL','RESET_SMTP_HOST','RESET_SMTP_USERNAME','RESET_SMTP_PASSWORD','RESET_MAIL_FROM'):
            env = {key:value for key,value in required.items() if key != missing}
            with patch.dict(os.environ, env, clear=True), self.assertRaises(RuntimeError):
                configure_runtime_security(Flask(__name__))
        with patch.dict(os.environ, required, clear=True):
            app = Flask(__name__); configure_runtime_security(app)
            self.assertTrue(app.config['SECURITY_TOKEN_RECOVERY'])
            self.assertTrue(app.config['SECURITY_SESSION_REVOCATION'])
            self.assertFalse(app.config['SECURITY_DELIVERY_CANDIDATES'])

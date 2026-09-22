"""Feature fixtures: SQLite in memory, real templates, CSRF and all HTTP blueprints."""
import re
import secrets
from flask import g
import test_themes
from extensions import limiter
from models import db, SecurityQuestion


class FeatureFixture:
    def setUp(self):
        test_themes.ThemeSettingsTest.setUp(self)
        self.app.config.update(ALLOWED_EXTENSIONS={'jpg', 'jpeg', 'png', 'webp'},
                               RATELIMIT_STORAGE_URI='memory://')
        limiter.init_app(self.app)
        limiter.reset()
        self.question = SecurityQuestion(question='Pregunta de prueba')
        db.session.add(self.question)
        db.session.commit()
        self.password = 'Strong!' + secrets.token_hex(12)

    def tearDown(self):
        limiter.reset()
        test_themes.ThemeSettingsTest.tearDown(self)

    def login_as(self, user):
        g.pop('_login_user', None)
        g.pop('csrf_token', None)
        with self.client.session_transaction() as session:
            if user:
                session['_user_id'] = str(user.id)
            else:
                session.pop('_user_id', None)

    def token(self, path='/privacy'):
        g.pop('csrf_token', None)
        response = self.client.get(path)
        assert response.status_code == 200, response.status_code
        return re.search(r'name="(?:csrf_token|csrf-token)"[^>]*?(?:value|content)="([^"]+)"', response.text).group(1)

    def registration(self, role='business', accept=True):
        self.login_as(None)
        data = dict(username='newmerchant', email='newmerchant@example.com', phone='0981000000',
                    password=self.password, confirm_password=self.password, account_type=role,
                    security_question_id=self.question.id, security_answer='respuesta',
                    csrf_token=self.token('/register'))
        if accept:
            data['accept_legal'] = 'y'
        return self.client.post('/register', data=data)

    def pending(self):
        self.business.approval_status = 'pending'
        self.business.is_active = False
        db.session.commit()
        return self.business

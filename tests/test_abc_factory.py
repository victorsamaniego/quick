"""Real application, all three flags, no inherited secrets or external services."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ABCFactoryTest(unittest.TestCase):
    def test_real_factory_token_reset_revokes_existing_login_with_csrf(self):
        root = Path(__file__).resolve().parents[1]
        env = {key:os.environ[key] for key in ('PATH','SYSTEMROOT','TEMP','TMP') if key in os.environ}
        env.update(DATABASE_URL='sqlite:///:memory:', FLASK_ENV='testing', FLASK_DEBUG='0', PYTHONUTF8='1',
            CLOUDINARY_CLOUD_NAME='', CLOUDINARY_API_KEY='', CLOUDINARY_API_SECRET='',
            SECURITY_TOKEN_RECOVERY='true', SECURITY_SESSION_REVOCATION='true', SECURITY_DELIVERY_CANDIDATES='true',
            PUBLIC_BASE_URL='https://quickgo.test', TRUSTED_HOSTS='localhost', RATELIMIT_STORAGE_URI='memory://',
            RESET_SMTP_HOST='smtp.example.test', RESET_SMTP_USERNAME='synthetic', RESET_MAIL_FROM='no-reply@example.test')
        script = r'''
import os, secrets, re
os.environ['SECRET_KEY'] = secrets.token_urlsafe(40)
os.environ['RESET_SMTP_PASSWORD'] = secrets.token_urlsafe(32)
from app import app
from flask_login import login_required
from models import db, User
from auth_tokens import issue_reset_token, PasswordResetToken
app.config['TESTING'] = True
@app.route('/abc-private')
@login_required
def private(): return 'ok'
def csrf(response):
    assert response.status_code == 200
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)
password = secrets.token_urlsafe(32)+'aA1!'
with app.app_context():
    assert str(db.engine.url) == 'sqlite:///:memory:'
    db.create_all()
    user = User(username='abc-buyer',email='buyer@example.test',phone='000000000')
    user.set_password(password); db.session.add(user); db.session.commit(); user_id = user.id
client = app.test_client()
response = client.post('/login',data={'username':'abc-buyer','password':password,
    'remember_me':'y','csrf_token':csrf(client.get('/login'))})
assert response.status_code == 302
assert client.get('/abc-private').status_code == 200
old_remember = client.get_cookie('remember_token').value
with app.app_context(): raw = issue_reset_token(user_id)
recover = app.test_client(); page = recover.get('/recover/token'); token = csrf(page)
assert 'no-store' in page.headers['Cache-Control']
assert page.headers['Referrer-Policy'] == 'no-referrer'
new_password = secrets.token_urlsafe(32)+'aA1!'
form = dict(reset_token=raw,new_password=new_password,confirm_password=new_password)
assert recover.post('/recover/token',data=form).status_code == 400
assert recover.post('/recover/token',data={**form,'csrf_token':token}).status_code == 302
assert client.get('/abc-private').status_code == 302
replay = app.test_client(); replay.set_cookie('remember_token',old_remember)
assert replay.get('/abc-private').status_code == 302
assert recover.post('/recover/token',data={**form,'csrf_token':token}).status_code == 400
with app.app_context():
    assert db.session.get(User,user_id).check_password(new_password)
    assert PasswordResetToken.query.one().used_at is not None
'''
        result = subprocess.run([sys.executable, '-X', 'utf8', '-X', 'faulthandler', '-c', script],
            cwd=root, env=env, capture_output=True, timeout=90)
        # Failure diagnostics intentionally omit captured bodies/configuration.
        self.assertEqual(result.returncode, 0, f'Isolated ABC factory failed, exit={result.returncode}')

"""Real Flask factory smoke test in a clean subprocess and in-memory SQLite only."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class FactorySecurityTest(unittest.TestCase):
    def test_real_factory_auth_csrf_private_response_and_checkout(self):
        root = Path(__file__).resolve().parents[1]
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP') if key in os.environ}
        env.update(DATABASE_URL='sqlite:///:memory:', FLASK_ENV='testing', FLASK_DEBUG='0',
                   PYTHONUTF8='1', CLOUDINARY_CLOUD_NAME='', CLOUDINARY_API_KEY='',
                   CLOUDINARY_API_SECRET='', RATELIMIT_STORAGE_URI='memory://',
                   TRUSTED_HOSTS='localhost', PUBLIC_BASE_URL='https://quickgo.test')
        script = r'''
import os, secrets, re
os.environ['SECRET_KEY'] = secrets.token_urlsafe(40)
from app import app
from models import db, User, Business, Product, Order
from extensions import limiter
from security import private_credential_response
app.config['TESTING'] = True
@app.route('/security-test-private')
def probe(): return private_credential_response(secrets.token_urlsafe(32), 'Prueba', '/')
def token(response):
    assert response.status_code == 200
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)
with app.app_context():
    assert str(db.engine.url) == 'sqlite:///:memory:'
    db.create_all()
    password = secrets.token_urlsafe(32)
    business = Business(name='Smoke Shop', slug='smoke', requires_subscription=False,
                        latitude=-25, longitude=-57)
    db.session.add(business); db.session.flush()
    users = []
    for role in ('buyer', 'seller', 'driver', 'superadmin'):
        user = User(username=role, email=role+'@example.test', phone='000',
                    is_admin=role=='seller', is_delivery=role=='driver',
                    is_super_admin=role=='superadmin',
                    business_id=business.id if role=='seller' else None)
        user.set_password(password); db.session.add(user); users.append(user)
    product = Product(name='Smoke Product', price=100, stock=3, business_id=business.id)
    db.session.add(product); db.session.commit()
    product_id = product.id
for role in ('buyer', 'seller', 'driver', 'superadmin'):
    with app.app_context(): limiter.reset()
    client = app.test_client()
    csrf_token = token(client.get('/login'))
    response = client.post('/login?next=https://attacker.test', data={
        'username':role, 'password':password, 'remember_me':'y', 'csrf_token':csrf_token})
    assert response.status_code == 302, (role, response.status_code)
    assert 'attacker.test' not in response.location
    with client.session_transaction() as session: assert '_user_id' in session
    assert bool(client.get_cookie('remember_token')) == (role == 'buyer')
    if role == 'buyer':
        assert client.post(f'/cart/add/{product_id}').status_code == 400
        assert client.post(f'/cart/add/{product_id}', data={'csrf_token':csrf_token}).status_code == 302
        csrf_token = token(client.get('/order/create'))
        response = client.post('/order/create', data={'csrf_token':csrf_token,
            'client_latitude':'-25', 'client_longitude':'-57', 'destination_confirmed':'yes',
            'shipping_address':'Destino de prueba', 'shipping_phone':'00000000',
            'shipping_reference':'Entrada', 'payment_method':'cash'})
        assert response.status_code == 302
        with app.app_context():
            assert Order.query.count() == 1
            assert db.session.get(Product, product_id).stock == 2
    csrf_token = token(client.get('/logout'))
    with client.session_transaction() as session: assert '_user_id' in session
    assert client.post('/logout', data={'csrf_token':csrf_token}).status_code == 302
    with client.session_transaction() as session: assert '_user_id' not in session
response = app.test_client().get('/security-test-private')
assert 'no-store' in response.headers['Cache-Control']
assert response.headers['Referrer-Policy'] == 'no-referrer'
assert "default-src 'none'" in response.headers['Content-Security-Policy']
assert '<script' not in response.text
'''
        result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', script], cwd=root,
                                env=env, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

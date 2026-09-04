import sys
import os
from pathlib import Path
import unittest
from math import degrees
from unittest.mock import patch
sys.path.insert(0, os.environ.get('QUICK_TEST_SOURCE', str(Path(__file__).resolve().parents[1])))
from flask import Flask
from flask_login import LoginManager
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
from models import db, User, Business, Product
import routes

class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% block content %}{% endblock %}{% block extra_js %}{% endblock %}'}), FileSystemLoader(str(Path(__import__('models').__file__).parent / 'templates'))])
        self.app.jinja_env.filters['smart_image'] = lambda value: value
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        # Ephemeral session signing material; no stored credentials.
        self.app.secret_key = __import__('secrets').token_bytes(32)
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda uid: db.session.get(User, int(uid)))
        self.app.register_blueprint(routes.main_bp)
        self.app.register_blueprint(routes.super_admin_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.admin = User(username='admin-test', email='admin@example.test', is_super_admin=True)
        self.buyer = User(username='buyer-test', email='buyer@example.test')
        for user in (self.admin, self.buyer):
            user.phone = '000000000'
            user.set_password(__import__('secrets').token_urlsafe(32))
        self.business = Business(name='Coverage Shop', slug='coverage', latitude=-25, longitude=-57, delivery_radius_km=10)
        db.session.add_all([self.admin, self.buyer, self.business])
        db.session.flush()
        db.session.add(Product(name='Coverage Product', business_id=self.business.id, price=100, stock=3))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.buyer.id)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def check_distance(self, km, visible):
        lat = -25 + degrees(km / 6371)
        response = self.client.post('/api/update-user-location', json={'latitude': str(lat), 'longitude': '-57'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['negocios_count'], int(visible))
        for url in ['/', '/products']:
            with patch.object(routes, 'render_template', side_effect=lambda template, **kw: {'businesses': [n['business'].name for n in kw['negocios_cercanos']], 'products': [p.name for p in kw['products']] }):
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['businesses'], ['Coverage Shop'] if visible else [])
            self.assertEqual(response.json['products'], ['Coverage Product'] if visible else [])
            html = self.client.get(url)
            self.assertEqual(html.status_code, 200)
            self.assertEqual('Coverage Shop' in html.text, visible)
            self.assertEqual('Coverage Product' in html.text, visible)
        self.assertAlmostEqual(routes.calcular_distancia_negocio_km(-25, -57, lat, -57), km, places=8)

    def test_5km_visible(self):
        self.check_distance(5, True)

    def test_20km_hidden(self):
        self.check_distance(20, False)

    def test_zero_and_invalid(self):
        self.business.latitude = 0
        self.business.longitude = 0
        db.session.commit()
        self.assertEqual(self.client.post('/api/update-user-location', json={'latitude': 0, 'longitude': 0}).json['negocios_count'], 1)
        for lat in [None, 'bad', 'nan', 91]:
            self.assertEqual(self.client.post('/api/update-user-location', json={'latitude': lat, 'longitude': 0}).status_code, 400)

    def test_null_business_does_not_hide_valid(self):
        db.session.add(Business(name='Missing', slug='missing'))
        db.session.commit()
        self.check_distance(5, True)
        self.business.delivery_radius_km = None
        db.session.commit()
        self.assertEqual(routes.obtener_negocios_cercanos(-25, -57), [])

    def test_create_edit_save_coverage(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id)
        data = dict(name='New Shop', slug='new-shop', latitude='-25.1', longitude='-57.2', delivery_radius_km='10')
        self.assertEqual(self.client.post('/super-admin/businesses/new', data=data).status_code, 302)
        business = Business.query.filter_by(slug='new-shop').one()
        self.assertEqual((business.latitude, business.longitude, business.delivery_radius_km), (-25.1, -57.2, 10))
        data.update(latitude='0', longitude='0', delivery_radius_km='15', is_active='on')
        self.assertEqual(self.client.post(f'/super-admin/businesses/{business.id}/edit', data=data).status_code, 302)
        self.assertEqual((business.latitude, business.longitude, business.delivery_radius_km), (0, 0, 15))

if __name__ == '__main__':
    unittest.main(verbosity=2)

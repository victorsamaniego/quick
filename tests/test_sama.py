import re
import unittest
from pathlib import Path
from flask import g
from werkzeug.datastructures import MultiDict
import test_merchant_coverage
import test_realtime
from extensions import csrf
from models import db, User, Product, Notification, NotificationRecipient


class PublicCatalogTest(unittest.TestCase):
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as
    def setUp(self):
        test_merchant_coverage.MerchantCoverageTest.setUp(self)
        csrf.init_app(self.app)
        self.app.config['SECURITY_ENFORCE_COVERAGE'] = True
        self.client = self.app.test_client()
        g.pop('_login_user', None)
        self.product = Product.query.filter_by(business_id=self.business.id).one()

    def locate(self, lat=-25, lon=-57):
        with self.client.session_transaction() as session:
            session['user_latitude'], session['user_longitude'] = lat, lon

    def test_anonymous_home_search_detail_and_private_stock(self):
        self.locate()
        self.product.stock = 714
        db.session.commit()
        for url in ['/', '/products?search=Coverage', f'/product/{self.product.id}']:
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            self.assertIn(self.product.name, page.text)
            self.assertNotIn('714', page.text)
        self.assertNotIn(self.product.name, self.client.get('/products?search=absent').text)

    def test_closed_and_sold_out_remain_browsable(self):
        self.locate()
        self.business.is_open = False
        db.session.commit()
        self.assertIn('Cerrado', self.client.get('/products').text)
        self.assertEqual(self.client.get(f'/product/{self.product.id}').status_code, 200)
        self.business.is_open = True
        self.product.stock = 0
        db.session.commit()
        # Preserve the existing catalog rule that excludes zero-stock products.
        self.assertNotIn(self.product.name, self.client.get('/products').text)
        self.assertIn('Agotado', self.client.get(f'/product/{self.product.id}').text)

    def test_public_location_post_and_coverage_gold(self):
        page = self.client.get('/products')
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
        # Empty catalogs have no purchase form, so obtain a token from the login.
        if token is None:
            token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', self.client.get('/login').text)
        response = self.client.post('/api/update-user-location', json={'latitude':-25,'longitude':-57}, headers={'X-CSRFToken':token.group(1)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f'/product/{self.product.id}').status_code, 200)
        with self.client.session_transaction() as session:
            session['user_location'] = {'latitude':0,'longitude':0}
            session['user_latitude'],session['user_longitude']=0,0
        self.assertNotIn(self.product.name, self.client.get('/products').text)
        self.assertEqual(self.client.get(f'/product/{self.product.id}').status_code, 400)
        self.business.is_quickgold = True
        db.session.commit()
        self.assertIn(self.product.name, self.client.get('/products').text)
        self.assertEqual(self.client.get(f'/product/{self.product.id}').status_code, 200)

    def test_anonymous_purchase_goes_to_safe_get_destination(self):
        self.locate()
        token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',self.client.get('/products').text).group(1)
        response=self.client.post(f'/cart/add/{self.product.id}',data={'csrf_token':token})
        self.assertEqual(response.status_code,302)
        self.assertIn('/login?next=/product/', response.location)
        with self.client.session_transaction() as session:
            self.assertFalse(session.get('cart'))
            self.assertTrue(any('iniciá sesión' in message for _,message in session['_flashes']))


class SegmentedNotificationsTest(unittest.TestCase):
    setUp = test_realtime.RealtimeTest.setUp
    tearDown = test_realtime.RealtimeTest.tearDown
    login_as = test_realtime.RealtimeTest.login_as
    connect = test_realtime.RealtimeTest.connect
    messages = test_realtime.RealtimeTest.messages

    def setup_csrf(self):
        csrf.init_app(self.app)
        self.login_as(self.admin)
        page=self.client.get('/super-admin/notifications/new')
        self.assertEqual(page.status_code,200)
        return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',page.text).group(1)

    def send_notification(self, audiences, token=None):
        self.login_as(self.admin)
        data=MultiDict([('title','Aviso '+','.join(audiences)),('message','Mensaje de prueba'),*[("audiences",a) for a in audiences]])
        if token:data.add('csrf_token',token)
        return self.client.post('/super-admin/notifications/new',data=data)

    def test_all_independent_and_multiple_audiences_http_and_socket(self):
        roles={'customer':self.buyer,'business':self.seller,'delivery':self.driver}
        sockets={role:self.connect(user) for role,user in roles.items()}
        token=self.setup_csrf()
        for groups in [('customer',),('business',),('delivery',),('customer','business'),('business','delivery'),('customer','delivery'),tuple(roles)]:
            self.assertEqual(self.send_notification(groups,token).status_code,302)
            notification=Notification.query.order_by(Notification.id.desc()).first()
            ids=[r.user_id for r in notification.recipients]
            self.assertEqual(len(ids),len(set(ids)))
            for role,user in roles.items():
                self.assertEqual(user.id in ids,role in groups)
                events=self.messages(sockets[role],'superadmin_notification')
                self.assertEqual(len(events),int(role in groups))
                self.login_as(user)
                snapshot=self.client.get('/api/notifications')
                self.assertEqual(snapshot.status_code,200)
                visible=[item['notification_id'] for item in snapshot.json['notifications']]
                self.assertEqual(notification.id in visible,role in groups)
                page=self.client.get(f'/notificacion/{notification.id}')
                self.assertEqual(page.status_code,200 if role in groups else 404)
                if events:
                    self.assertEqual(events[0]['audience'],role)
                    self.assertNotIn('user_id',events[0])
                    self.assertNotIn('recipients',events[0])
            self.assertNotIn(self.admin.id,ids)

    def test_only_superadmin_and_csrf(self):
        token=self.setup_csrf()
        self.assertEqual(self.send_notification(['customer']).status_code,400)
        for user in (self.buyer,self.seller,self.driver):
            self.login_as(user)
            self.assertEqual(self.client.post('/super-admin/notifications/new',data={'csrf_token':token,'audiences':'customer','title':'No','message':'No'}).status_code,302)
        self.assertEqual(Notification.query.count(),0)

    def test_validation_plain_text_and_read_post(self):
        token=self.setup_csrf()
        self.login_as(self.admin)
        base={'csrf_token':token,'audiences':'customer','title':'Title','message':'Text'}
        for change in ({'title':''},{'title':'x'*201},{'message':'x'*2001},{'audiences':'unknown'},{'audiences':''},{'user_id':self.buyer.id},{'message':'\x00bad'}):
            self.assertEqual(self.client.post('/super-admin/notifications/new',data={**base,**change}).status_code,400)
        self.assertEqual(Notification.query.count(),0)
        self.assertEqual(self.client.post('/super-admin/notifications/new',data={**base,'message':'<script>alert(1)</script>'}).status_code,302)
        notification=Notification.query.one()
        self.login_as(self.buyer)
        page=self.client.get(f'/notificacion/{notification.id}')
        self.assertIn('&lt;script&gt;',page.text)
        recipient=NotificationRecipient.query.filter_by(user_id=self.buyer.id).one()
        self.assertFalse(recipient.is_read)
        url=f'/notificacion/{notification.id}/read'
        self.assertEqual(self.client.post(url).status_code,400)
        self.assertEqual(self.client.post(url,data={'csrf_token':token}).status_code,302)
        self.assertTrue(recipient.is_read)

    def test_role_change_revokes_previous_audience_and_overlap_is_delivery(self):
        token=self.setup_csrf()
        self.assertEqual(self.send_notification(['customer'],token).status_code,302)
        notification=Notification.query.one()
        self.buyer.is_delivery=True
        self.seller.is_delivery=True
        db.session.commit()
        self.login_as(self.buyer)
        self.assertEqual(self.client.get(f'/notificacion/{notification.id}').status_code,404)
        self.assertEqual(self.send_notification(['business'],token).status_code,302)
        latest=Notification.query.order_by(Notification.id.desc()).first()
        self.assertNotIn(self.seller.id,[r.user_id for r in latest.recipients])


class IconAssetsTest(unittest.TestCase):
    def test_local_font_css_and_real_flash_html(self):
        root=Path(__file__).parents[1]
        base=(root/'templates/base.html').read_text(encoding='utf-8')
        self.assertIn("filename='vendor/bootstrap-icons/bootstrap-icons.min.css'",base)
        self.assertNotIn('https://cdn.jsdelivr.net/npm/bootstrap-icons',base)
        css=(root/'static/vendor/bootstrap-icons/bootstrap-icons.min.css').read_text(encoding='utf-8')
        for icon in ('bi-exclamation-triangle','bi-info-circle','bi-check-circle','bi-x-circle','bi-bell','bi-shop'):
            self.assertIn('.'+icon+'::before',css)
        for font in ('bootstrap-icons.woff','bootstrap-icons.woff2'):
            self.assertGreater((root/'static/vendor/bootstrap-icons/fonts'/font).stat().st_size,10000)
        self.assertNotIn("{{ '<i",base)
        self.assertNotIn('|safe',base)
        self.assertIn('quickgo-shell',base)
        known = set(re.findall(r'\.(bi-[a-z0-9-]+)::before', css))
        for template in (root/'templates').rglob('*.html'):
            names = set(re.findall(r'\bbi-[a-z0-9-]+', template.read_text(encoding='utf-8')))
            self.assertFalse(names - known, f'{template.name}: {names - known}')
        self.assertIn('col-6 col-md-3 col-xl-2',(root/'templates/products.html').read_text(encoding='utf-8'))

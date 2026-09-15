import base64
import re
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, Mock
from flask import g
from extensions import csrf
from models import db
import web_push
import test_realtime


class WebPushTest(unittest.TestCase):
    tearDown = test_realtime.RealtimeTest.tearDown
    login_as = test_realtime.RealtimeTest.login_as
    checkout = test_realtime.RealtimeTest.checkout

    def setUp(self):
        test_realtime.RealtimeTest.setUp(self)
        csrf.init_app(self.app)
        self.app.config.update(WEB_PUSH_ENABLED=True, WEB_PUSH_VAPID_PUBLIC_KEY='test-public',
            WEB_PUSH_VAPID_PRIVATE_KEY='test-private', WEB_PUSH_CONTACT='mailto:test@example.test')
        self.subscription = {'endpoint': 'https://fcm.googleapis.com/push/test-device', 'keys': {
            'p256dh': base64.urlsafe_b64encode(bytes([4]) + bytes(64)).decode().rstrip('='),
            'auth': base64.urlsafe_b64encode(bytes(16)).decode().rstrip('=')}}
        self.login_as(self.buyer)

    def post(self, route, data):
        response = self.client.get('/logout')
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)
        return self.client.post('/api/push/' + route, json=data, headers={'X-CSRFToken': token})

    def test_login_and_csrf_required(self):
        self.assertEqual(self.client.post('/api/push/subscribe', json=self.subscription).status_code, 400)
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', self.client.get('/logout').text).group(1)
        with self.client.session_transaction() as session: session.pop('_user_id', None)
        g.pop('_login_user', None)
        self.assertIn(self.client.post('/api/push/subscribe', json=self.subscription, headers={'X-CSRFToken':token}).status_code, (302, 401))

    def test_duplicate_device_unsubscribe_and_ownership(self):
        for _ in range(2):
            response = self.post('subscribe', self.subscription)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(web_push.PushSubscription.query.count(), 1)
        device = response.json['device']
        self.login_as(self.outsider)
        self.assertEqual(self.post('unsubscribe', {'device': device}).status_code, 200)
        self.assertEqual(web_push.PushSubscription.query.count(), 1)
        self.login_as(self.buyer)
        self.assertEqual(self.post('unsubscribe', {'device': device}).status_code, 200)
        self.assertEqual(web_push.PushSubscription.query.count(), 0)

    def test_disabled_and_incomplete_config_are_noops(self):
        for changes in ({'WEB_PUSH_ENABLED':False}, {'WEB_PUSH_ENABLED':True, 'WEB_PUSH_VAPID_PRIVATE_KEY':None}):
            self.app.config.update(changes)
            self.assertFalse(self.client.get('/api/push/config').json['enabled'])
            self.assertEqual(self.post('subscribe', self.subscription).status_code, 503)
            with patch.object(web_push._executor, 'submit') as submit:
                web_push.enqueue('new_order', {'order_id':1}, ['business_1']); submit.assert_not_called()

    def test_ssrf_huge_payload_and_untrusted_identity_rejected(self):
        for endpoint in ['http://127.0.0.1/', 'https://fcm.googleapis.com.evil.test/a',
                         'https://localhost/a', 'https://fcm.googleapis.com:444/a',
                         'https://name@fcm.googleapis.com/a', 'https://fcm.googleapis.com/a#x']:
            self.assertEqual(self.post('subscribe', {**self.subscription, 'endpoint': endpoint}).status_code, 400)
        self.assertEqual(self.post('subscribe', {**self.subscription, 'user_id':self.outsider.id}).status_code, 400)
        self.assertEqual(self.post('subscribe', {'padding': 'x'*10000}).status_code, 413)

    def test_410_and_404_remove_subscription_without_logging_capability(self):
        from pywebpush import WebPushException
        for code in (404, 410):
            self.post('subscribe', self.subscription)
            row = web_push.PushSubscription.query.one()
            with patch('pywebpush.webpush', side_effect=WebPushException('sensitive endpoint', response=Mock(status_code=code))):
                web_push.send_to_subscription(row, {'title':'Test'})
            self.assertEqual(web_push.PushSubscription.query.count(), 0)

    def test_private_room_audience_and_foreground_suppression(self):
        self.post('subscribe', self.subscription)
        row = web_push.PushSubscription.query.one()
        with patch.object(web_push, 'send_to_subscription') as send:
            web_push.deliver('new_order', {'order_id':1}, [f'business_{self.other.id}']); send.assert_not_called()
            with self.app.test_request_context('/'):
                web_push.deliver('superadmin_notification', {'notification_id':1}, [f'user_{self.buyer.id}'])
            self.assertEqual(send.call_count, 1)
            row.visible_at = datetime.now(timezone.utc); db.session.commit()
            web_push.deliver('superadmin_notification', {'notification_id':2}, [f'user_{self.buyer.id}'])
            self.assertEqual(send.call_count, 1)

    def test_presence_is_authenticated_owned_and_boolean(self):
        device = self.post('subscribe', self.subscription).json['device']
        self.assertEqual(self.post('presence', {'device':device, 'visible':True}).status_code, 200)
        self.assertIsNotNone(web_push.PushSubscription.query.one().visible_at)
        self.assertEqual(self.post('presence', {'device':device, 'visible':'true'}).status_code, 400)
        self.login_as(self.outsider)
        self.assertEqual(self.post('presence', {'device':device, 'visible':False}).status_code, 404)

    def test_all_events_have_internal_destination_and_no_private_body(self):
        payload = {'order_id':1, 'request_id':2, 'notification_id':3, 'channel':'delivery_chat_1',
                   'event_id':'event-1', 'status':'shipped', 'message':{'id':4, 'message':'private'}}
        with self.app.test_request_context('/'):
            for event in web_push.EVENTS:
                data = web_push.push_payload(event, payload, self.buyer)
                self.assertTrue(data['url'].startswith('/'))
                self.assertNotIn('private', data['body'])

    def test_real_vapid_encryption_and_https_transport_without_network(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        from py_vapid import Vapid
        vapid = Vapid(); vapid.generate_keys()
        self.app.config['WEB_PUSH_VAPID_PRIVATE_KEY'] = vapid
        public = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        self.subscription['keys']['p256dh'] = base64.urlsafe_b64encode(public).decode().rstrip('=')
        self.post('subscribe', self.subscription)
        row = web_push.PushSubscription.query.one()
        response = Mock(status_code=201, text='')
        with patch('requests.sessions.Session.request', return_value=response) as transport:
            web_push.send_to_subscription(row, {'title':'Synthetic notice', 'event_id':'crypto-test'})
            transport.assert_called_once()
            args = transport.call_args.kwargs
            self.assertFalse(args['allow_redirects'])
            self.assertEqual(args['timeout'], 5)
            self.assertNotIn(b'Synthetic notice', args['data'])
            self.assertTrue(any(key.lower() == 'authorization' for key in args['headers']))

    def test_logout_removes_device_even_when_push_is_disabled(self):
        self.post('subscribe', self.subscription)
        self.app.config['WEB_PUSH_ENABLED'] = False
        page = self.client.get('/logout')
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text).group(1)
        self.assertEqual(self.client.post('/logout', data={'csrf_token':token}).status_code, 302)
        self.assertEqual(web_push.PushSubscription.query.count(), 0)

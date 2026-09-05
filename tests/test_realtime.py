"""Isolated SQLite tests. Never import app.py or its production configuration."""
import unittest
from unittest.mock import patch
from flask import g
import test_order_destination
from models import db, User, Order, ChatMessage
from realtime import socketio, register_realtime, publish_status


class RealtimeTest(unittest.TestCase):
    login_as = test_order_destination.OrderDestinationTest.login_as
    checkout = test_order_destination.OrderDestinationTest.checkout

    def setUp(self):
        test_order_destination.OrderDestinationTest.setUp(self)
        socketio.init_app(self.app, async_mode='threading', manage_session=True)
        register_realtime(self.app)
        self.sockets = []
        self.driver = User(username='rt-driver', email='rt-driver@example.test', phone='000',
                           password_hash=self.buyer.password_hash, is_delivery=True)
        self.outsider = User(username='rt-outsider', email='rt-outsider@example.test', phone='000',
                            password_hash=self.buyer.password_hash, is_admin=True, business_id=self.other.id)
        db.session.add_all([self.driver, self.outsider])
        db.session.commit()

    def tearDown(self):
        for client in self.sockets:
            g.pop('_login_user', None)
            if client.is_connected():
                client.disconnect()
        test_order_destination.OrderDestinationTest.tearDown(self)

    def connect(self, user):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(user.id)
        g.pop('_login_user', None)
        sock = socketio.test_client(self.app, flask_test_client=client)
        self.assertTrue(sock.is_connected())
        self.sockets.append(sock)
        return sock

    def join(self, sock, room):
        g.pop('_login_user', None)
        return sock.emit('join', {'room': room}, callback=True)

    def create_order(self):
        data = self.checkout()
        self.assertEqual(self.client.post('/order/create', data=data).status_code, 302)
        order = Order.query.one()
        order.delivery_driver_id = self.driver.id
        db.session.commit()
        return order

    def messages(self, sock, event):
        return [item['args'][0] for item in sock.get_received() if item['name'] == event]

    def send(self, order):
        self.login_as(self.buyer)
        return self.client.post(f'/api/chat/order/{order.id}/send', json={'message': 'Hola en vivo'})

    def test_three_authorized_roles_join_and_outsider_cannot(self):
        order = self.create_order()
        for user in [self.buyer, self.seller, self.driver]:
            self.assertTrue(self.join(self.connect(user), f'order_{order.id}')['success'])
        outsider = self.connect(self.outsider)
        for room in [f'order_{order.id}', f'order_chat_{order.id}', f'business_{self.business.id}', 'admin']:
            self.assertFalse(self.join(outsider, room)['success'])

    def test_outsider_cannot_read_send_or_load_history(self):
        order = self.create_order()
        self.login_as(self.outsider)
        self.assertEqual(self.client.get(f'/chat/order/{order.id}').status_code, 302)
        self.assertEqual(self.client.get(f'/api/chat/order/{order.id}/messages').status_code, 403)
        self.assertEqual(self.client.post(f'/api/chat/order/{order.id}/send', json={'message': 'No'}).status_code, 403)
        self.assertEqual(ChatMessage.query.count(), 0)

    def test_persisted_id_delivered_once_to_all_authorized_clients(self):
        order = self.create_order()
        sockets = [self.connect(user) for user in [self.buyer, self.seller, self.driver]]
        for sock in sockets:
            self.assertTrue(self.join(sock, f'order_chat_{order.id}')['success'])
        outsider = self.connect(self.outsider)
        response = self.send(order)
        self.assertEqual(response.status_code, 200)
        persisted = ChatMessage.query.one()
        self.assertEqual(response.json['message']['id'], persisted.id)
        for sock in sockets:
            events = self.messages(sock, 'new_chat_message')
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['message']['id'], persisted.id)
        self.assertEqual(self.messages(outsider, 'new_chat_message'), [])

    def test_other_order_room_does_not_receive(self):
        order = self.create_order()
        other_order = Order(user_id=self.outsider.id, business_id=self.other.id, total_amount=100,
                            shipping_address='Other', shipping_phone='000', status='pending')
        db.session.add(other_order)
        db.session.commit()
        outsider = self.connect(self.outsider)
        self.assertTrue(self.join(outsider, f'order_{other_order.id}')['success'])
        self.send(order)
        self.assertEqual(self.messages(outsider, 'new_chat_message'), [])

    def test_reconnect_history_persists_without_replaying_live_events(self):
        order = self.create_order()
        sock = self.connect(self.seller)
        sock.disconnect()
        self.send(order)
        sock = self.connect(self.seller)
        self.assertTrue(self.join(sock, f'order_{order.id}')['success'])
        self.assertEqual(self.messages(sock, 'new_chat_message'), [])
        self.login_as(self.seller)
        for _ in range(2):
            history = self.client.get(f'/api/chat/order/{order.id}/messages').json['messages']
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['id'], ChatMessage.query.one().id)
        self.assertEqual(self.client.get(f'/api/chat/order/{order.id}/messages?after={history[0]["id"]}').json['messages'], [])

    def test_revoked_driver_does_not_receive_future_messages(self):
        order = self.create_order()
        sock = self.connect(self.driver)
        self.join(sock, f'order_{order.id}')
        order.delivery_driver_id = None
        db.session.commit()
        self.send(order)
        self.assertEqual(self.messages(sock, 'new_chat_message'), [])

    def test_new_order_goes_only_to_correct_business_after_persistence(self):
        seller = self.connect(self.seller)
        other = self.connect(self.outsider)
        from realtime import publish as real_publish
        def check_commit(event, payload, rooms):
            if event == 'new_order':
                self.assertIsNotNone(db.session.get(Order, payload['order_id']))
                self.assertFalse(db.session.new)
            return real_publish(event, payload, rooms)
        with patch('routes.publish', side_effect=check_commit):
            order = self.create_order()
        events = self.messages(seller, 'new_order')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['order_id'], order.id)
        self.assertEqual(events[0]['business_id'], self.business.id)
        self.assertEqual(self.messages(other, 'new_order'), [])

    def test_failed_commit_emits_nothing(self):
        data = self.checkout()
        seller = self.connect(self.seller)
        self.login_as(self.buyer)
        with patch.object(db.session, 'commit', side_effect=RuntimeError('test transaction failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/order/create', data=data)
        db.session.rollback()
        self.assertEqual(Order.query.count(), 0)
        self.assertEqual(self.messages(seller, 'new_order'), [])

    def test_failed_message_commit_emits_nothing(self):
        order = self.create_order()
        seller = self.connect(self.seller)
        with patch.object(db.session, 'commit', side_effect=RuntimeError('test transaction failure')):
            with self.assertRaises(RuntimeError):
                self.send(order)
        db.session.rollback()
        self.assertEqual(ChatMessage.query.count(), 0)
        self.assertEqual(self.messages(seller, 'new_chat_message'), [])

    def test_completion_only_for_real_transition(self):
        order = self.create_order()
        buyer = self.connect(self.buyer)
        outsider = self.connect(self.outsider)
        order.status = 'delivered'
        db.session.commit()
        publish_status(order, 'shipped')
        publish_status(order, 'delivered')
        self.assertEqual(len(self.messages(buyer, 'order_status_update')), 1)
        self.assertEqual(self.messages(outsider, 'order_status_update'), [])

    def test_private_room_boundaries(self):
        order = self.create_order()
        buyer = self.connect(self.buyer)
        self.assertFalse(self.join(buyer, f'delivery_chat_{order.id}')['success'])
        self.assertFalse(self.join(buyer, f'support_{self.business.id}')['success'])
        self.assertTrue(self.join(self.connect(self.driver), f'delivery_chat_{order.id}')['success'])
        self.assertTrue(self.join(self.connect(self.admin), f'support_{self.business.id}')['success'])

    def test_anonymous_socket_is_rejected(self):
        g.pop('_login_user', None)
        sock = socketio.test_client(self.app, flask_test_client=self.app.test_client())
        self.assertFalse(sock.is_connected())

    def test_malformed_message_is_rejected(self):
        order = self.create_order()
        self.login_as(self.buyer)
        for data in [[], {'message': 2}, {'message': ' '}]:
            self.assertEqual(self.client.post(f'/api/chat/order/{order.id}/send', json=data).status_code, 400)
        self.assertEqual(ChatMessage.query.count(), 0)

    def test_delivery_eligibility_uses_order_destination_and_denies_unrelated_driver(self):
        from datetime import datetime, timedelta, timezone
        from models import DeliveryRequest
        from routes import eligible_delivery
        order = self.create_order()
        order.delivery_driver_id = None
        request = DeliveryRequest(order_id=order.id, business_id=self.business.id, search_radius=5,
                                  expires_at=datetime.now(timezone.utc) + timedelta(minutes=2))
        db.session.add(request)
        db.session.commit()
        with patch.object(User, 'find_nearby_deliveries', return_value=[]) as nearby:
            self.assertFalse(eligible_delivery(self.driver, request))
            nearby.assert_called_with(order.client_latitude, order.client_longitude, 5, business_id=None)
        with patch.object(User, 'find_nearby_deliveries', return_value=[{'delivery': self.driver, 'distance': 1}]):
            self.assertTrue(eligible_delivery(self.driver, request))
        request.status = 'accepted'
        self.assertFalse(eligible_delivery(self.driver, request))

    def test_private_message_is_persisted_and_not_leaked_to_buyer(self):
        from models import DeliveryBusinessChat
        order = self.create_order()
        driver = self.connect(self.driver)
        self.join(driver, f'delivery_chat_{order.id}')
        buyer = self.connect(self.buyer)
        self.join(buyer, f'order_{order.id}')
        self.login_as(self.seller)
        response = self.client.post(f'/chat-delivery/{order.id}', data={'message': 'Retirar paquete'})
        self.assertEqual(response.status_code, 302)
        events = self.messages(driver, 'private_chat_message')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['message']['id'], DeliveryBusinessChat.query.one().id)
        self.assertEqual(self.messages(buyer, 'private_chat_message'), [])

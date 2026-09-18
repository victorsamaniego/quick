"""Tests aislados del sistema de caja. No acceden a producción."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import test_merchant_coverage
from models import db, User, Order, Product, CashSession, CashMovement
from cash_register_service import calculate_session_summary, close_cash_session, get_session_orders


class CashRegisterTest(unittest.TestCase):
    setUp = test_merchant_coverage.MerchantCoverageTest.setUp
    tearDown = test_merchant_coverage.MerchantCoverageTest.tearDown
    login_as = test_merchant_coverage.MerchantCoverageTest.login_as

    def enable_cash(self):
        self.business.cash_register_enabled = True
        self.business.requires_subscription = False
        db.session.commit()

    def open_session(self, amount='100000'):
        self.enable_cash()
        session = CashSession(
            business_id=self.business.id,
            opened_by_user_id=self.seller.id,
            opened_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            opening_amount=Decimal(amount)
        )
        db.session.add(session)
        db.session.commit()
        return session

    def order(self, amount, method, status, minutes=1):
        when = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        order = Order(
            user_id=self.buyer.id,
            business_id=self.business.id,
            total_amount=float(amount),
            shipping_address='Test',
            shipping_phone='000',
            status=status,
            payment_method=method
        )
        if status == 'delivered':
            order.delivered_at = when
        elif status == 'picked_up':
            order.picked_up_at = when
        db.session.add(order)
        db.session.commit()
        return order

    def test_disabled_by_default_and_direct_url_blocked(self):
        self.assertFalse(self.business.cash_register_enabled)
        self.login_as(self.seller)
        response = self.client.get('/admin/cash-register')
        self.assertEqual(response.status_code, 302)

    def test_open_zero_and_only_one_open_session(self):
        self.enable_cash()
        self.login_as(self.seller)

        self.assertEqual(
            self.client.post('/admin/cash-register/open',
                             data={'opening_amount': '0'}).status_code,
            302
        )

        self.assertEqual(
            CashSession.query.filter_by(
                business_id=self.business.id,
                closed_at=None
            ).count(),
            1
        )

        self.client.post(
            '/admin/cash-register/open',
            data={'opening_amount': '50000'}
        )

        self.assertEqual(
            CashSession.query.filter_by(
                business_id=self.business.id,
                closed_at=None
            ).count(),
            1
        )

    def test_negative_opening_rejected(self):
        self.enable_cash()
        self.login_as(self.seller)

        self.client.post(
            '/admin/cash-register/open',
            data={'opening_amount': '-1'}
        )

        self.assertEqual(CashSession.query.count(), 0)

    def test_movements_calculate_expected_cash(self):
        session = self.open_session('100000')

        db.session.add_all([
            CashMovement(
                cash_session_id=session.id,
                business_id=self.business.id,
                created_by_user_id=self.seller.id,
                type='manual_income',
                amount=Decimal('50000'),
                description='Ingreso'
            ),
            CashMovement(
                cash_session_id=session.id,
                business_id=self.business.id,
                created_by_user_id=self.seller.id,
                type='expense',
                amount=Decimal('20000'),
                description='Gasto'
            ),
            CashMovement(
                cash_session_id=session.id,
                business_id=self.business.id,
                created_by_user_id=self.seller.id,
                type='withdrawal',
                amount=Decimal('10000'),
                description='Retiro'
            )
        ])
        db.session.commit()

        summary = calculate_session_summary(session)

        self.assertEqual(summary['manual_income'], Decimal('50000.00'))
        self.assertEqual(summary['expenses'], Decimal('20000.00'))
        self.assertEqual(summary['withdrawals'], Decimal('10000.00'))
        self.assertEqual(summary['expected_cash'], Decimal('120000.00'))

    def test_cash_qr_transfer_and_unknown(self):
        session = self.open_session('100000')

        self.order('50000', 'cash', 'delivered', 4)
        self.order('70000', 'qr', 'picked_up', 3)
        self.order('30000', 'transfer', 'delivered', 2)
        unknown_order = self.order('25000', 'cash', 'picked_up', 1)
        unknown_order.payment_method = None
        db.session.commit()

        summary = calculate_session_summary(session)

        self.assertEqual(summary['cash_sales'], Decimal('50000.00'))
        self.assertEqual(summary['qr_sales'], Decimal('70000.00'))
        self.assertEqual(summary['transfer_sales'], Decimal('30000.00'))
        self.assertEqual(summary['other_sales'], Decimal('25000.00'))
        self.assertEqual(summary['total_sales'], Decimal('175000.00'))

        # Solo efectivo físico aumenta la gaveta.
        self.assertEqual(summary['expected_cash'], Decimal('150000.00'))

    def test_pending_does_not_count(self):
        session = self.open_session()

        order = Order(
            user_id=self.buyer.id,
            business_id=self.business.id,
            total_amount=99999,
            shipping_address='Pending',
            shipping_phone='000',
            status='pending',
            payment_method='cash'
        )
        db.session.add(order)
        db.session.commit()

        self.assertEqual(
            calculate_session_summary(session)['cash_sales'],
            Decimal('0.00')
        )

    def test_completed_without_real_timestamp_does_not_count(self):
        session = self.open_session()

        order = Order(
            user_id=self.buyer.id,
            business_id=self.business.id,
            total_amount=50000,
            shipping_address='Historico',
            shipping_phone='000',
            status='delivered',
            payment_method='cash'
        )
        db.session.add(order)
        db.session.commit()

        self.assertNotIn(order, get_session_orders(session))
        self.assertEqual(
            calculate_session_summary(session)['cash_sales'],
            Decimal('0.00')
        )

    def test_close_snapshots_and_difference(self):
        session = self.open_session('100000')
        self.order('50000', 'cash', 'delivered')

        close_cash_session(
            session,
            Decimal('149000'),
            self.seller.id
        )

        self.assertIsNotNone(session.closed_at)
        self.assertEqual(
            Decimal(session.expected_cash_at_close),
            Decimal('150000.00')
        )
        self.assertEqual(
            Decimal(session.declared_cash),
            Decimal('149000.00')
        )
        self.assertEqual(
            Decimal(session.difference_at_close),
            Decimal('-1000.00')
        )
        self.assertEqual(session.difference_status, 'faltante')

    def test_closed_cash_rejects_new_movement(self):
        session = self.open_session()
        close_cash_session(
            session,
            Decimal('100000'),
            self.seller.id
        )

        self.login_as(self.seller)

        self.client.post(
            '/admin/cash-register/movements/new',
            data={
                'type': 'expense',
                'amount': '1000',
                'description': 'No debe guardarse'
            }
        )

        self.assertEqual(CashMovement.query.count(), 0)

    def test_other_business_history_isolated(self):
        self.enable_cash()

        self.other.cash_register_enabled = True
        self.other.requires_subscription = False

        outsider = User(
            username='cash-outsider',
            email='cash-outsider@example.test',
            phone='000',
            password_hash=self.buyer.password_hash,
            is_admin=True,
            business_id=self.other.id
        )
        db.session.add(outsider)
        db.session.flush()

        other_session = CashSession(
            business_id=self.other.id,
            opened_by_user_id=outsider.id,
            opened_at=datetime.now(timezone.utc),
            opening_amount=Decimal('1000'),
            closed_at=datetime.now(timezone.utc),
            closed_by_user_id=outsider.id,
            declared_cash=Decimal('1000'),
            expected_cash_at_close=Decimal('1000'),
            difference_at_close=Decimal('0')
        )

        db.session.add(other_session)
        db.session.commit()

        self.login_as(self.seller)

        response = self.client.get(
            f'/admin/cash-register/session/{other_session.id}'
        )

        self.assertEqual(response.status_code, 404)

    def test_stock_does_not_change(self):
        product = Product.query.filter_by(
            business_id=self.business.id
        ).first()

        stock_before = product.stock

        session = self.open_session()

        db.session.add(
            CashMovement(
                cash_session_id=session.id,
                business_id=self.business.id,
                created_by_user_id=self.seller.id,
                type='manual_income',
                amount=Decimal('1000'),
                description='Ingreso'
            )
        )
        db.session.commit()

        close_cash_session(
            session,
            Decimal('101000'),
            self.seller.id
        )

        db.session.refresh(product)
        self.assertEqual(product.stock, stock_before)

    def business_payload(self, cash_enabled=False):
        data = {
            'name': self.business.name,
            'slug': self.business.slug,
            'latitude': str(self.business.latitude),
            'longitude': str(self.business.longitude),
            'delivery_radius_km': str(self.business.delivery_radius_km),
            'commission_rate': '0.10',
            'delivery_fee_base': '5000',
            'delivery_fee_per_km': '1000',
            'is_active': 'on'
        }
        if cash_enabled:
            data['cash_register_enabled'] = 'on'
        return data

    def test_super_admin_can_enable_cash_register(self):
        self.assertFalse(self.business.cash_register_enabled)
        self.login_as(self.admin)
        response = self.client.post(
            f'/super-admin/businesses/{self.business.id}/edit',
            data=self.business_payload(cash_enabled=True)
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.business)
        self.assertTrue(self.business.cash_register_enabled)

    def test_seller_cannot_enable_own_cash_register(self):
        self.assertFalse(self.business.cash_register_enabled)
        self.login_as(self.seller)
        response = self.client.post(
            f'/super-admin/businesses/{self.business.id}/edit',
            data=self.business_payload(cash_enabled=True)
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.business)
        self.assertFalse(self.business.cash_register_enabled)

    def test_super_admin_cannot_disable_with_open_session(self):
        session = self.open_session()
        self.login_as(self.admin)
        response = self.client.post(
            f'/super-admin/businesses/{self.business.id}/edit',
            data=self.business_payload(cash_enabled=False)
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.business)
        self.assertTrue(self.business.cash_register_enabled)
        self.assertIsNone(session.closed_at)

    def test_disable_after_close_preserves_history_and_reenable(self):
        session = self.open_session()
        close_cash_session(session, Decimal('100000'), self.seller.id)
        session_id = session.id

        self.login_as(self.admin)
        self.client.post(
            f'/super-admin/businesses/{self.business.id}/edit',
            data=self.business_payload(cash_enabled=False)
        )
        db.session.refresh(self.business)
        self.assertFalse(self.business.cash_register_enabled)
        self.assertIsNotNone(db.session.get(CashSession, session_id))

        self.client.post(
            f'/super-admin/businesses/{self.business.id}/edit',
            data=self.business_payload(cash_enabled=True)
        )
        db.session.refresh(self.business)
        self.assertTrue(self.business.cash_register_enabled)
        self.assertIsNotNone(db.session.get(CashSession, session_id))


if __name__ == '__main__':
    unittest.main(verbosity=2)



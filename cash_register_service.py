"""Cash register management service: calculations, snapshots, session lifecycle."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from models import db, Order, CashSession, CashMovement, Business


MAX_CASH_AMOUNT = Decimal("9999999999999.99")

def to_decimal(val):
    if val is None:
        return Decimal("0.00")
    amount = val if isinstance(val, Decimal) else Decimal(str(val))
    if not amount.is_finite():
        raise ValueError("Monto no finito.")
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(amount) > MAX_CASH_AMOUNT:
        raise ValueError("Monto fuera del rango permitido.")
    return amount

def normalize_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_open_session(business_id, for_update=False):
    """Retrieve the currently open cash session for business_id, if any."""
    query = CashSession.query.filter_by(business_id=business_id, closed_at=None)
    if for_update:
        query = query.with_for_update()
    return query.first()


def get_order_completion_time(order):
    """Determine the effective timestamp when the order was completed (picked up or delivered)."""
    if order.status == 'picked_up':
        return normalize_utc(order.picked_up_at)
    if order.status == 'delivered':
        return normalize_utc(order.delivered_at)
    return None


def get_session_orders(session):
    """Fetch completed orders completed within the session timeframe."""
    start_time = normalize_utc(session.opened_at)
    end_time = normalize_utc(session.closed_at) if session.closed_at else datetime.now(timezone.utc)

    candidate_orders = Order.query.filter(
        Order.business_id == session.business_id,
        Order.status.in_(['delivered', 'picked_up'])
    ).all()

    session_orders = []
    for o in candidate_orders:
        comp_time = get_order_completion_time(o)
        if comp_time and start_time <= comp_time <= end_time:
            session_orders.append(o)

    session_orders.sort(
        key=lambda o: get_order_completion_time(o) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    return session_orders


def calculate_session_summary(session, orders=None):
    """Calculate monetary totals and expected cash for the session."""
    if session.closed_at is not None:
        return {
            'opening_amount': to_decimal(session.opening_amount),
            'cash_sales': to_decimal(session.cash_sales_total),
            'qr_sales': to_decimal(session.qr_sales_total),
            'transfer_sales': to_decimal(session.transfer_sales_total),
            'card_sales': to_decimal(session.card_sales_total),
            'other_sales': to_decimal(session.other_sales_total),
            'total_sales': to_decimal(session.total_sales),
            'manual_income': to_decimal(session.manual_income_total),
            'expenses': to_decimal(session.expense_total),
            'withdrawals': to_decimal(session.withdrawal_total),
            'expected_cash': to_decimal(session.expected_cash_at_close),
            'declared_cash': to_decimal(session.declared_cash),
            'difference': to_decimal(session.difference_at_close),
            'difference_status': session.difference_status,
            'difference_label': session.difference_label,
            'difference_badge_color': session.difference_badge_color,
            'orders_count': len(orders) if orders is not None else 0
        }

    if orders is None:
        orders = get_session_orders(session)

    cash_sales = Decimal('0.00')
    qr_sales = Decimal('0.00')
    transfer_sales = Decimal('0.00')
    card_sales = Decimal('0.00')
    other_sales = Decimal('0.00')

    for order in orders:
        amt = to_decimal(order.total_amount)
        method = (order.payment_method or 'unknown').lower().strip()
        if method == 'cash':
            cash_sales += amt
        elif method == 'qr':
            qr_sales += amt
        elif method == 'transfer':
            transfer_sales += amt
        elif method == 'card':
            card_sales += amt
        else:
            other_sales += amt

    total_sales = cash_sales + qr_sales + transfer_sales + card_sales + other_sales

    manual_income = Decimal('0.00')
    expenses = Decimal('0.00')
    withdrawals = Decimal('0.00')

    for mov in session.movements:
        amt = to_decimal(mov.amount)
        if mov.type == 'manual_income':
            manual_income += amt
        elif mov.type == 'expense':
            expenses += amt
        elif mov.type == 'withdrawal':
            withdrawals += amt

    opening = to_decimal(session.opening_amount)
    expected_cash = opening + cash_sales + manual_income - expenses - withdrawals

    return {
        'opening_amount': opening,
        'cash_sales': cash_sales,
        'qr_sales': qr_sales,
        'transfer_sales': transfer_sales,
        'card_sales': card_sales,
        'other_sales': other_sales,
        'total_sales': total_sales,
        'manual_income': manual_income,
        'expenses': expenses,
        'withdrawals': withdrawals,
        'expected_cash': expected_cash,
        'declared_cash': None,
        'difference': None,
        'difference_status': None,
        'difference_label': None,
        'difference_badge_color': None,
        'orders_count': len(orders)
    }


def close_cash_session(session, declared_cash, closed_by_user_id):
    """Atomically close the cash session, persisting calculated snapshots and difference."""
    if session.closed_at is not None:
        raise ValueError("La sesión de caja ya fue cerrada.")

    declared_cash_dec = to_decimal(declared_cash)
    if declared_cash_dec < Decimal('0.00'):
        raise ValueError("El monto declarado no puede ser negativo.")

    orders = get_session_orders(session)
    summary = calculate_session_summary(session, orders=orders)
    expected_cash_dec = summary['expected_cash']
    diff_dec = declared_cash_dec - expected_cash_dec

    session.cash_sales_total = summary['cash_sales']
    session.qr_sales_total = summary['qr_sales']
    session.transfer_sales_total = summary['transfer_sales']
    session.card_sales_total = summary['card_sales']
    session.other_sales_total = summary['other_sales']
    session.manual_income_total = summary['manual_income']
    session.expense_total = summary['expenses']
    session.withdrawal_total = summary['withdrawals']
    session.total_sales = summary['total_sales']
    session.expected_cash_at_close = expected_cash_dec
    session.declared_cash = declared_cash_dec
    session.difference_at_close = diff_dec
    session.closed_by_user_id = closed_by_user_id
    session.closed_at = datetime.now(timezone.utc)

    db.session.commit()
    return session




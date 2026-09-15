"""Global analytics, accessible only through the super-admin route."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from models import db, Business, Product, Order, OrderItem


def analytics_queries():
    now = datetime.now(timezone.utc)
    revenue = db.session.query(
        Business.id.label('business_id'), Business.name,
        func.coalesce(func.sum(Order.total_amount), 0).label('revenue')
    ).outerjoin(Order, (Business.id == Order.business_id)
                & (Order.created_at >= now - timedelta(days=30))
                & (Order.status.in_(['delivered', 'picked_up'])))\
        .group_by(Business.id, Business.name).order_by(func.sum(Order.total_amount).desc())
    daily = db.session.query(func.date(Order.created_at).label('date'),
                             func.count(Order.id).label('order_count'))\
        .filter(Order.created_at >= now - timedelta(days=7))\
        .group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at))
    products = db.session.query(
        Product.id.label('product_id'), Product.name,
        Business.id.label('business_id'), Business.name.label('business_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('sold')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
        .join(Order, (OrderItem.order_id == Order.id) & (Order.business_id == Product.business_id))\
        .join(Business, Product.business_id == Business.id)\
        .filter(Order.status.in_(['delivered', 'picked_up']))\
        .group_by(Product.id, Product.name, Business.id, Business.name)\
        .order_by(func.sum(OrderItem.quantity).desc()).limit(10)
    statuses = db.session.query(Order.status, func.count(Order.id).label('order_count'))\
        .group_by(Order.status).order_by(Order.status)
    return revenue, daily, products, statuses


def analytics_data():
    revenue, daily, products, statuses = analytics_queries()
    return dict(
        revenue_by_business=[dict(row._mapping) for row in revenue.all()],
        orders_by_day=[{'date': str(row.date), 'order_count': row.order_count} for row in daily.all()],
        top_products=[dict(row._mapping) for row in products.all()],
        order_statuses=[{'status': row.status or 'Sin estado', 'status_label': Order(status=row.status).status_label or 'Sin estado', 'order_count': row.order_count} for row in statuses.all()],
        active_business_count=Business.query.filter_by(is_active=True).count(),
    )

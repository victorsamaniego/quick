"""Read-only inventory valuation at current sale prices; no schema changes."""
from decimal import Decimal, InvalidOperation, localcontext

# Matches Product.is_low_stock; zero stock is reported separately.
LOW_STOCK_THRESHOLD = 10


def nonnegative_decimal(value):
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else Decimal(0)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def inventory_summary(products):
    rows = []
    with localcontext() as context:
        context.prec = 400  # Safely covers the existing Float column's finite range.
        for product in products:
            stock = int(nonnegative_decimal(product.stock))
            price = nonnegative_decimal(product.price)
            rows.append(dict(product=product, stock=stock, price=price, value=price * stock))
        return dict(rows=rows, product_count=len(rows),
                    units=sum(row['stock'] for row in rows),
                    value=sum((row['value'] for row in rows), Decimal(0)),
                    out_of_stock=sum(row['stock'] == 0 for row in rows),
                    low_stock=sum(0 < row['stock'] < LOW_STOCK_THRESHOLD for row in rows))


def inventory_money(value):
    return 'GS ' + format(value, ',.0f').replace(',', '.')

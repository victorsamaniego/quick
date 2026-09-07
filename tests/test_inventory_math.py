import unittest
from decimal import Decimal
from types import SimpleNamespace
from inventory import inventory_summary, inventory_money


class InventoryMathTest(unittest.TestCase):
    def test_totals_zero_and_decimal(self):
        products = [SimpleNamespace(stock=18, price=8500), SimpleNamespace(stock=2, price=65000),
                    SimpleNamespace(stock=0, price=200), SimpleNamespace(stock=4, price=0)]
        result = inventory_summary(products)
        self.assertEqual((result['product_count'], result['units'], result['value']), (4, 24, Decimal(283000)))
        self.assertEqual((result['out_of_stock'], result['low_stock']), (1, 2))
        self.assertEqual(result['value'], sum(row['value'] for row in result['rows']))
        self.assertEqual(inventory_money(result['value']), 'GS 283.000')
        self.assertEqual(inventory_summary([SimpleNamespace(stock=3, price=0.1)])['value'], Decimal('0.3'))

    def test_invalid_and_empty(self):
        result = inventory_summary([SimpleNamespace(stock=None, price=None), SimpleNamespace(stock=-2, price=float('nan')),
                                    SimpleNamespace(stock='bad', price=float('inf'))])
        self.assertEqual((result['units'], result['value']), (0, 0))
        self.assertEqual(inventory_summary([])['product_count'], 0)

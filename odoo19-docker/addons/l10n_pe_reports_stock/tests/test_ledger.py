import datetime

from odoo.tests.common import TransactionCase, tagged

from ..services import stock_ledger

COMMON = {"per": "20261000", "pid": 1, "estab": "0000", "existence": "01", "code": "P001",
          "unspsc": False, "desc": "Producto de prueba", "uom": "07"}


def ev(day, op, qty_in, qty_out, val_in, val_out):
    return {"date": datetime.date(2026, 10, day), "cuo": "S%d" % day, "corr": "M%d" % day, "doc_type": "00",
            "series": "0", "number": "0", "op": op, "qty_in": qty_in, "qty_out": qty_out,
            "val_in": val_in, "val_out": val_out}


@tagged("post_install", "-at_install")
class TestLedger(TransactionCase):
    def test_physical_and_valued(self):
        events = [ev(5, "02", 20, 0, 120.0, 0.0), ev(9, "01", 0, 15, 0.0, 85.0)]
        start = datetime.date(2026, 10, 1)
        phys = stock_ledger.physical_rows(COMMON, 10, events, start)
        self.assertEqual(len(phys), 3)
        self.assertTrue(all(len(r) == 19 for r in phys))
        self.assertEqual(phys[0][13], "16")
        self.assertEqual(phys[2][17], "-15.00")
        val = stock_ledger.valued_rows(COMMON, "2", 10, 50.0, events, start)
        self.assertTrue(all(len(r) == 27 for r in val))
        self.assertEqual(val[-1][23], "15.0000")   # saldo cantidad
        self.assertEqual(val[-1][25], "85.00")     # saldo costo total

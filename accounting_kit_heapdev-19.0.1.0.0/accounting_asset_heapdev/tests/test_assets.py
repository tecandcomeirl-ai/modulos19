# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import AccKitCase, TODAY


@tagged("post_install", "-at_install", "heapdev_acckit")
class TestAccAssets(AccKitCase):

    def setUp(self):
        super().setUp()
        self.cat = self.env["acc.asset.category"].create({
            "name": "Test Equipment", "asset_type": "asset", "journal_id": self.misc.id,
            "account_asset_id": self.acc_fixed.id, "account_depreciation_id": self.acc_accum.id, "account_expense_id": self.acc_expense.id,
            "method": "linear", "method_number": 12, "method_period": 1, "prorata": False, "auto_post": True})

    def _asset(self, **kw):
        vals = {"name": "Laptop", "category_id": self.cat.id, "date": date(TODAY.year, 1, 1), "value": 1200.0}
        vals.update(kw)
        return self.env["acc.asset"].create(vals)

    def test_linear_board(self):
        asset = self._asset()
        asset.compute_depreciation_board()
        self.assertEqual(len(asset.line_ids), 12)
        self.assertTrue(all(abs(l.amount - 100.0) < 0.01 for l in asset.line_ids))
        self.assertAlmostEqual(sum(asset.line_ids.mapped("amount")), 1200.0, places=2)
        self.assertEqual(asset.line_ids[0].date, date(TODAY.year, 1, 31))
        self.assertEqual(asset.line_ids[-1].date, date(TODAY.year, 12, 31))

    def test_salvage_value(self):
        asset = self._asset(salvage_value=200.0)
        asset.compute_depreciation_board()
        self.assertAlmostEqual(sum(asset.line_ids.mapped("amount")), 1000.0, places=2)

    def test_prorata_first_period(self):
        asset = self._asset(date=date(TODAY.year, 1, 16), prorata=True)
        asset.compute_depreciation_board()
        self.assertEqual(len(asset.line_ids), 13)
        self.assertLess(asset.line_ids[0].amount, 100.0)
        self.assertAlmostEqual(sum(asset.line_ids.mapped("amount")), 1200.0, places=2)

    def test_degressive_board(self):
        asset = self._asset(method="degressive", degressive_factor=2.0, method_number=4, method_period=3)
        asset.compute_depreciation_board()
        amounts = asset.line_ids.mapped("amount")
        self.assertEqual(len(amounts), 4)
        self.assertGreater(amounts[0], amounts[-1] - 0.01)
        self.assertAlmostEqual(sum(amounts), 1200.0, places=2)

    def test_confirm_and_post_due(self):
        asset = self._asset()
        asset.action_confirm()
        self.assertEqual(asset.state, "open")
        asset.action_post_due(date(TODAY.year, 3, 31))
        moves = asset.line_ids.filtered("move_id").mapped("move_id")
        self.assertEqual(len(moves), 3)
        self.assertTrue(all(m.state == "posted" for m in moves))
        exp = moves.mapped("line_ids").filtered(lambda l: l.account_id == self.acc_expense)
        self.assertAlmostEqual(sum(exp.mapped("debit")), 300.0, places=2)

    def test_dispose(self):
        asset = self._asset()
        asset.action_confirm()
        wiz = self.env["acc.asset.dispose"].create({"asset_id": asset.id, "date": date(TODAY.year, 6, 30), "action": "dispose",
                                                    "loss_account_id": self.acc_expense.id, "gain_account_id": self.acc_income.id})
        wiz.action_confirm()
        self.assertEqual(asset.state, "close")
        self.assertTrue(asset.disposal_date)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self._asset(salvage_value=5000.0)

    def test_deferred_revenue_category(self):
        cat = self.env["acc.asset.category"].create({
            "name": "Test Deferred Revenue", "asset_type": "revenue", "journal_id": self.misc.id,
            "account_asset_id": self.acc_liab.id, "account_depreciation_id": self.acc_liab.id, "account_expense_id": self.acc_income.id,
            "method_number": 12, "method_period": 1, "prorata": False})
        asset = self.env["acc.asset"].create({"name": "Support contract", "category_id": cat.id, "asset_type": "revenue",
                                              "date": date(TODAY.year, 1, 1), "value": 12000.0})
        asset.action_confirm()
        asset.action_post_due(date(TODAY.year, 1, 31))
        move = asset.line_ids[0].move_id
        inc = move.line_ids.filtered(lambda l: l.account_id == self.acc_income)
        self.assertAlmostEqual(sum(inc.mapped("credit")), 1000.0, places=2)

    def test_auto_create_from_bill(self):
        self.acc_fixed.acc_asset_category_id = self.cat
        bill = self._invoice(date(TODAY.year, 2, 1), 2400.0, move_type="in_invoice", account=self.acc_fixed)
        assets = self.env["acc.asset"].search([("source_move_id", "=", bill.id)])
        self.assertEqual(len(assets), 1)
        self.assertAlmostEqual(assets.value, 2400.0, places=2)

    def test_schedule_report(self):
        self._asset().action_confirm()
        res = self.env["acc.report.engine"].get_report_html({"report": "assets"})
        self.assertIn("Laptop", res["html"])

# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AccKitCase, TODAY, V


@tagged("post_install", "-at_install", "heapdev_acckit")
class TestAccTools(AccKitCase):

    def test_full_accounting_groups(self):
        user_grp = self.env.ref("account.group_account_user")
        mgr = self.env.ref("account.group_account_manager")
        implied = mgr.implied_ids if "implied_ids" in mgr._fields else mgr.implied_group_ids
        self.assertIn(user_grp, implied)

    def test_recurring_entries_no_drift(self):
        rec = self.env["acc.recurring.entry"].create({
            "name": "Rent accrual", "journal_id": self.misc.id, "date_start": date(TODAY.year, 1, 31), "interval_type": "months",
            "line_ids": [(0, 0, {"account_id": self.acc_expense.id, "name": "Rent", "debit": 500.0}),
                         (0, 0, {"account_id": self.acc_liab.id, "name": "Rent payable", "credit": 500.0})]})
        rec.action_start()
        self.assertEqual(rec.state, "running")
        rec.action_generate(date(TODAY.year, 4, 30))
        dates = sorted(rec.move_ids.mapped("date"))
        self.assertEqual(dates, [date(TODAY.year, 1, 31), date(TODAY.year, 2, 28 if TODAY.year % 4 else 29), date(TODAY.year, 3, 31), date(TODAY.year, 4, 30)])
        self.assertTrue(all(m.state == "posted" for m in rec.move_ids))
        self.assertEqual(rec.next_date, date(TODAY.year, 5, 31))

    def test_recurring_unbalanced_rejected(self):
        rec = self.env["acc.recurring.entry"].create({
            "name": "Broken", "journal_id": self.misc.id, "date_start": TODAY, "interval_type": "months",
            "line_ids": [(0, 0, {"account_id": self.acc_expense.id, "name": "x", "debit": 10.0}),
                         (0, 0, {"account_id": self.acc_liab.id, "name": "y", "credit": 9.0})]})
        with self.assertRaises(Exception):
            rec.action_start()

    def _pdc(self, **kw):
        inv = self._invoice(TODAY - timedelta(days=5), 1050.0)
        vals = {"pdc_type": "receive", "partner_id": self.partner.id, "cheque_number": "CHQ-T1", "bank_name": "Test Bank",
                "date": TODAY, "cheque_date": TODAY + timedelta(days=30), "amount": 1050.0, "invoice_ids": [(6, 0, inv.ids)],
                "journal_id": self.bank.id, "misc_journal_id": self.misc.id, "pdc_account_id": self.acc_current.id}
        vals.update(kw)
        return self.env["acc.pdc"].create(vals), inv

    def test_pdc_register_clear(self):
        pdc, inv = self._pdc()
        self.assertNotEqual(pdc.name, "/")
        pdc.action_register()
        self.assertEqual(pdc.state, "registered")
        self.assertTrue(pdc.register_move_id)
        self.assertIn(inv.payment_state, ("paid", "in_payment"))
        pdc.action_clear()
        self.assertEqual(pdc.state, "cleared")
        self.assertTrue(pdc.clear_move_id)
        pdc_lines = (pdc.register_move_id | pdc.clear_move_id).mapped("line_ids").filtered(lambda l: l.account_id == self.acc_current)
        self.assertAlmostEqual(sum(pdc_lines.mapped("balance")), 0.0, places=2)

    def test_pdc_bounce_reopens_invoice(self):
        pdc, inv = self._pdc(cheque_number="CHQ-T2")
        pdc.action_register()
        pdc.action_bounce()
        self.assertEqual(pdc.state, "bounced")
        self.assertAlmostEqual(inv.amount_residual, 1050.0, places=2)

    def test_lock_date_wizard(self):
        wiz = self.env["acc.lock.date"].create({"tax_lock_date": date(TODAY.year - 2, 12, 31)})
        wiz.action_apply()
        self.assertEqual(self.company.tax_lock_date, date(TODAY.year - 2, 12, 31))

    def test_dashboard(self):
        self._entry(TODAY, self.acc_current, self.acc_income, 750.0)
        res = self.env["acc.report.engine"].get_report_html({"report": "dashboard"})
        self.assertIn("o_acc_kpi", res["html"])
        self.assertIn("<svg", res["html"])

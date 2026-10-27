# -*- coding: utf-8 -*-
from odoo.tests import tagged

from .common import AccKitCase, TODAY, Y0


@tagged("post_install", "-at_install", "heapdev_acckit")
class TestAccReports(AccKitCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env["acc.report.engine"]
        self._entry(TODAY, self.acc_current, self.acc_income, 1000.0, self.partner)
        self._entry(TODAY, self.acc_expense, self.acc_liab, 400.0, self.partner)

    def _opts(self, report, **kw):
        opts = {"report": report, "date_from": str(Y0), "date_to": str(TODAY)}
        opts.update(kw)
        return opts

    def test_every_report_renders(self):
        for key in self.engine._report_meta():
            res = self.engine.get_report_html(self._opts(key))
            self.assertIn("o_acc_report", res["html"], key)
            self.assertEqual(res["options"]["report"], key)

    def test_trial_balance_is_balanced(self):
        data = self.engine._compute(self.engine._normalize(self._opts("tb")))
        self.assertTrue(data["lines"])
        self.env.cr.execute("SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0) FROM account_move_line WHERE company_id = %s AND parent_state = 'posted'",
                            [self.company.id])
        debit, credit = self.env.cr.fetchone()
        self.assertAlmostEqual(debit, credit, places=2)
        html = self.engine.get_report_html(self._opts("tb"))["html"]
        self.assertIn("T90001", html)

    def test_profit_and_loss_contains_entries(self):
        html = self.engine.get_report_html(self._opts("pl", unfold_all=True))["html"]
        self.assertIn("Test Income", html)
        self.assertIn("Test Expense", html)

    def test_xlsx_export(self):
        for key in ("pl", "bs", "gl", "tb", "aged_receivable"):
            content, fname = self.engine.export_xlsx(self._opts(key))
            self.assertEqual(content[:2], b"PK", key)
            self.assertTrue(fname.endswith(".xlsx"))

    def test_drill_returns_journal_items(self):
        action = self.engine.action_drill(self._opts("gl"), {"type": "aml", "account_id": self.acc_income.id,
                                                               "date_from": str(Y0), "date_to": str(TODAY)})
        self.assertEqual(action["res_model"], "account.move.line")
        lines = self.env["account.move.line"].search(action["domain"])
        self.assertIn(self.acc_income, lines.mapped("account_id"))

    def test_comparison_and_filters(self):
        res = self.engine.get_report_html(self._opts("pl", comparison=1, posted_only=False, journal_ids=[self.misc.id]))
        self.assertIn("o_acc_report", res["html"])

    def test_pdf_action(self):
        action = self.engine.action_print_pdf(self._opts("bs"))
        # without a configured document layout Odoo first returns the layout wizard
        self.assertIn(action["type"], ("ir.actions.report", "ir.actions.act_window"))

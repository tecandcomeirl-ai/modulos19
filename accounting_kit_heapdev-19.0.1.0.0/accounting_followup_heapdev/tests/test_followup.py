# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.tests import tagged

from .common import AccKitCase, TODAY, V


@tagged("post_install", "-at_install", "heapdev_acckit")
class TestAccFollowup(AccKitCase):

    def setUp(self):
        super().setUp()
        Level = self.env["acc.followup.level"]
        self.levels = Level.search([("company_id", "=", self.company.id)], order="delay")
        if not self.levels:
            self.levels = Level.create([{"name": "L1", "delay": 7}, {"name": "L2", "delay": 30}, {"name": "L3", "delay": 60}])
        self.partner.email = "ar-test@example.com"

    def test_amounts_and_level(self):
        self._invoice(TODAY - timedelta(days=80), 500.0, due=TODAY - timedelta(days=45))
        self._invoice(TODAY, 300.0, due=TODAY + timedelta(days=30))
        p = self.partner
        p.invalidate_recordset() if hasattr(p, "invalidate_recordset") else p.invalidate_cache()
        self.assertAlmostEqual(p.acc_total_due, 800.0, places=2)
        self.assertAlmostEqual(p.acc_total_overdue, 500.0, places=2)
        self.assertEqual(p.acc_overdue_days, 45)
        expected = self.levels.filtered(lambda l: l.delay <= 45)[-1:]
        self.assertEqual(p.acc_followup_level_id, expected)

    def test_search_has_overdue(self):
        self._invoice(TODAY - timedelta(days=40), 200.0, due=TODAY - timedelta(days=10))
        found = self.env["res.partner"].search([("acc_has_overdue", "=", True)])
        self.assertIn(self.partner, found)
        not_found = self.env["res.partner"].search([("acc_has_overdue", "=", False), ("id", "=", self.partner.id)])
        self.assertFalse(not_found)

    def test_email_body_and_composer(self):
        inv = self._invoice(TODAY - timedelta(days=40), 200.0, due=TODAY - timedelta(days=10))
        body = str(self.partner._acc_email_body())
        self.assertIn(inv.name, body)
        action = self.partner.action_acc_followup_email()
        self.assertEqual(action["res_model"], "mail.compose.message")
        self.assertEqual(self.partner.acc_followup_last_date, TODAY)
        self.assertTrue(self.partner.acc_followup_next_date)

    def test_statement_report_html(self):
        self._invoice(TODAY - timedelta(days=40), 200.0, due=TODAY - timedelta(days=10))
        report = self.env.ref("accounting_followup_heapdev.action_report_acc_customer_statement")
        if V >= 16:
            html = self.env["ir.actions.report"]._render_qweb_html(report.report_name, self.partner.ids)[0]
        else:
            html = report._render_qweb_html(self.partner.ids)[0]
        self.assertIn(b"Heapdev Test Customer", html)

    def test_batch_run(self):
        self._invoice(TODAY - timedelta(days=100), 900.0, due=TODAY - timedelta(days=70))
        wiz = self.env["acc.followup.run"].create({"send_emails": True, "print_letters": False, "create_activities": True, "only_due": False})
        wiz.action_run()
        self.assertEqual(self.partner.acc_followup_last_date, TODAY)

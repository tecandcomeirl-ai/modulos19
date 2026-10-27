from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEdi(TransactionCase):
    def test_summary_naming_and_sequence(self):
        company = self.env.company
        vals = {"kind": "RC", "company_id": company.id, "reference_date": date(2026, 10, 5),
                "issue_date": date(2026, 10, 5)}
        first = self.env["sunat.summary"].create(vals)
        second = self.env["sunat.summary"].create(vals)
        self.assertEqual(first.name, "RC-20261005-1")
        self.assertEqual(second.name, "RC-20261005-2")

    def test_company_defaults(self):
        company = self.env.company
        self.assertEqual(company.sunat_auto_send, "off")
        self.assertEqual(company.sunat_boleta_mode, "individual")
        self.assertEqual(company.sunat_max_attempts, 5)

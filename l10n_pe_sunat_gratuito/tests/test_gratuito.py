from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGratuito(TransactionCase):
    def setUp(self):
        super().setUp()
        self.igv = self.env["account.tax"].create({
            "name": "IGV 18% test", "amount": 18.0, "amount_type": "percent", "type_tax_use": "sale",
            "sunat_tax_code": "1000", "sunat_afectacion": "10"})
        self.partner = self.env["res.partner"].create({"name": "Cliente", "vat": "20123456789"})

    def _move(self, free):
        vals = {"move_type": "out_invoice", "partner_id": self.partner.id,
                "invoice_line_ids": [(0, 0, {
                    "name": "Regalo", "quantity": 1, "price_unit": 800.0,
                    "tax_ids": [(6, 0, self.igv.ids)], "sunat_free_afect": free})]}
        return self.env["account.move"].create(vals)

    def test_free_line_values(self):
        line = self._move("15").invoice_line_ids[0]
        self.assertEqual(line.discount, 100.0)
        self.assertAlmostEqual(line.sunat_free_total, 800.0)
        self.assertAlmostEqual(line.sunat_free_tax, 144.0)
        self.assertAlmostEqual(line.price_total, 0.0)

    def test_regular_line_has_no_free_values(self):
        line = self._move(False).invoice_line_ids[0]
        self.assertEqual(line.sunat_free_total, 0.0)
        self.assertEqual(line.discount, 0.0)

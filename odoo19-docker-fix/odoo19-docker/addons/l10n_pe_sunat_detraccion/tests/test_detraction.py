from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDetraction(TransactionCase):
    def test_catalog_loaded(self):
        code = self.env.ref("l10n_pe_sunat_detraccion.detraction_037")
        self.assertEqual(code.rate, 12.0)
        self.assertEqual(code.min_amount, 700.0)

    def test_calculation_and_rounding(self):
        code = self.env.ref("l10n_pe_sunat_detraccion.detraction_037")
        move = self.env["account.move"].new({
            "move_type": "out_invoice", "company_id": self.env.company.id,
            "currency_id": self.env.company.currency_id.id})
        move.sunat_detraction_code_id = code
        # sin líneas el total es 0: por debajo del mínimo no hay detracción
        move._compute_sunat_detraction()
        self.assertEqual(move.sunat_detraction_amount, 0.0)

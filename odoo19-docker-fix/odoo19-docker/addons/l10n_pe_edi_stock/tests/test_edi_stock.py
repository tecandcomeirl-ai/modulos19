from odoo.tests.common import TransactionCase, tagged

from ..models.uom import guess_uom_codes


@tagged("post_install", "-at_install")
class TestEdiStock(TransactionCase):
    def test_uom_guess(self):
        self.assertEqual(guess_uom_codes("kg"), ("KGM", "01"))
        self.assertEqual(guess_uom_codes("Unidades"), ("NIU", "07"))
        self.assertEqual(guess_uom_codes("raro"), ("NIU", "99"))

    def test_vehicle_plate_normalized(self):
        veh = self.env["l10n_pe.vehicle"].create({"plate": "abc-123"})
        self.assertEqual(veh.plate, "ABC123")

    def test_driver_name(self):
        drv = self.env["l10n_pe.driver"].create({
            "first_name": "Juan", "last_name": "Pérez", "doc_number": "12345678", "license": "Q123"})
        self.assertIn("Juan", drv.name)

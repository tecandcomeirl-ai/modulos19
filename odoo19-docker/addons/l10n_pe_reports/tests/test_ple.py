from odoo.tests.common import TransactionCase, tagged

from ..services import ple_common as pc


@tagged("post_install", "-at_install")
class TestPle(TransactionCase):
    def test_file_name(self):
        # LE + RUC + AAAAMM + 00 + libro + 00 + O + I + M + 1
        self.assertEqual(pc.file_name("20123456789", 2026, 5, "140100", True),
                         "LE2012345678920260500140100001111.txt")
        self.assertEqual(pc.file_name("20123456789", 2026, 5, "050100", False),
                         "LE2012345678920260500050100001011.txt")

    def test_record_format(self):
        self.assertEqual(pc.record(["a", "", "3"]), "a||3|")
        self.assertEqual(pc.clean("A|B&C\nD"), "A B C D")

    def test_empty_book_is_generated(self):
        rep = self.env["l10n_pe.ple.report"].create({"book": "050300", "year": 2020, "month": "1"})
        rep.company_id.vat = "20000000001"
        rep.action_generate()
        self.assertEqual(rep.state, "done")
        self.assertTrue(rep.txt_filename.startswith("LE20000000001202001"))

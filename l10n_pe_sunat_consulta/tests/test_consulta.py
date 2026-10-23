from odoo.tests.common import TransactionCase, tagged

from ..models.account_move import VENDOR_NUM_RE
from ..services import consulta_client


@tagged("post_install", "-at_install")
class TestConsulta(TransactionCase):
    def test_vendor_number_regex(self):
        match = VENDOR_NUM_RE.search("FFI E001-00000045")
        self.assertEqual(match.groups(), ("E001", "00000045"))

    def test_catalogs(self):
        self.assertEqual(consulta_client.ESTADO_RUC["00"], "ACTIVO")
        self.assertEqual(consulta_client.COND_DOMI["00"], "HABIDO")

    def test_wizard_requires_credentials(self):
        company = self.env.company
        company.sunat_api_client_id = False
        with self.assertRaises(consulta_client.ConsultaError):
            consulta_client.get_token(company)

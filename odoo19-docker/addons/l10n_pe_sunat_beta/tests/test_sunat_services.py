import io
import zipfile

from odoo.tests.common import TransactionCase, tagged

from ..models.account_tax import sunat_guess_from_tax
from ..services import soap_client, ubl_builder

CDR = b"""<?xml version="1.0" encoding="UTF-8"?>
<ar:ApplicationResponse xmlns:ar="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cac:DocumentResponse><cac:Response>
  <cbc:ResponseCode>0</cbc:ResponseCode>
  <cbc:Description>La Factura numero F001-00000001, ha sido aceptada</cbc:Description>
 </cac:Response></cac:DocumentResponse></ar:ApplicationResponse>"""


@tagged("post_install", "-at_install")
class TestSunatServices(TransactionCase):
    def test_amount_in_words(self):
        self.assertIn("CON 50/100 SOLES", ubl_builder.amount_in_words(118.50, "PEN"))

    def test_cdr_parsing(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("R-20000000001-01-F001-00000001.xml", CDR)
        code, desc = soap_client.parse_cdr(buf.getvalue())
        self.assertEqual(code, "0")
        self.assertIn("aceptada", desc)

    def test_tax_guess(self):
        self.assertEqual(sunat_guess_from_tax("IGV 18%", 18), ("1000", "10"))
        self.assertEqual(sunat_guess_from_tax("Exonerado", 0), ("9997", "20"))
        self.assertEqual(sunat_guess_from_tax("Inafecto", 0), ("9998", "30"))

    def test_series_number(self):
        move = self.env["account.move"].new({"name": "FFI F001-123"})
        self.assertEqual(move._sunat_series_number(), ("F001", "00000123"))

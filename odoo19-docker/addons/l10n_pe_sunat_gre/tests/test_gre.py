from lxml import etree

from odoo.tests.common import TransactionCase, tagged

from ..services import gre_builder


@tagged("post_install", "-at_install")
class TestGre(TransactionCase):
    def test_build_and_validate(self):
        partner = self.env["res.partner"].create({"name": "Cliente GRE", "vat": "20123456789"})
        gre = self.env["sunat.gre"].create({
            "partner_id": partner.id, "partner_vat": "20123456789", "partner_doc_type": "6",
            "number": "1", "series": "T001", "gross_weight": 10.0, "packages": 1,
            "origin_ubigeo": "150101", "origin_address": "Av. Origen 123",
            "dest_ubigeo": "040101", "dest_address": "Calle Destino 456",
            "driver_doc": "12345678", "driver_first_name": "Juan", "driver_last_name": "Perez",
            "driver_license": "Q12345678", "vehicle_plate": "ABC123",
            "line_ids": [(0, 0, {"description": "Caja de prueba", "quantity": 5})],
        })
        gre.company_id.vat = "20000000001"
        xml = gre_builder.build_despatch(gre)
        root = etree.fromstring(xml)
        self.assertEqual(etree.QName(root).localname, "DespatchAdvice")
        self.assertEqual(gre.name, "T001-1")

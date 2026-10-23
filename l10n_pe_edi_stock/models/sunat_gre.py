from odoo import api, fields, models

from odoo.addons.l10n_pe_sunat_gre.models.sunat_gre import partner_ubigeo  # noqa: F401


class SunatGre(models.Model):
    _inherit = "sunat.gre"

    driver_id = fields.Many2one("l10n_pe.driver", string="Conductor registrado")
    vehicle_id = fields.Many2one("l10n_pe.vehicle", string="Vehículo registrado")
    carrier_id = fields.Many2one("res.partner", string="Transportista registrado")
    related_doc_type = fields.Char(compute="_compute_related_doc", store=True)
    related_doc_number = fields.Char(string="Comprobante relacionado", compute="_compute_related_doc", store=True)

    @api.depends("move_id", "move_id.name", "move_id.sunat_doc_type")
    def _compute_related_doc(self):
        for gre in self:
            number = doc_type = False
            if gre.move_id and gre.move_id.sunat_doc_type in ("01", "03"):
                try:
                    series, num = gre.move_id._sunat_series_number()
                    number = "%s-%s" % (series, int(num))
                    doc_type = gre.move_id.sunat_doc_type
                except Exception:  # noqa: BLE001
                    number = doc_type = False
            gre.related_doc_number = number
            gre.related_doc_type = doc_type

    @api.onchange("driver_id")
    def _onchange_driver_id(self):
        for gre in self:
            drv = gre.driver_id
            if drv:
                gre.driver_doc_type = drv.doc_type
                gre.driver_doc = drv.doc_number
                gre.driver_first_name = drv.first_name
                gre.driver_last_name = drv.last_name
                gre.driver_license = drv.license

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        for gre in self:
            if gre.vehicle_id:
                gre.vehicle_plate = gre.vehicle_id.plate

    @api.onchange("carrier_id")
    def _onchange_carrier_id(self):
        for gre in self:
            if gre.carrier_id:
                gre.carrier_vat = gre.carrier_id.vat
                gre.carrier_name = gre.carrier_id.name

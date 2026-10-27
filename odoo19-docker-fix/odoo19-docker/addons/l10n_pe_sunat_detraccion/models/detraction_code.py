from odoo import api, fields, models


class SunatDetractionCode(models.Model):
    _name = "sunat.detraction.code"
    _description = "Bien o servicio sujeto a detracción (Catálogo 54)"
    _order = "code"

    code = fields.Char(string="Código", size=3, required=True)
    name = fields.Char(string="Descripción", required=True)
    rate = fields.Float(string="Tasa (%)", digits=(5, 2), required=True)
    min_amount = fields.Float(string="Monto mínimo (S/)", default=700.0,
                              help="La detracción aplica cuando el importe de la operación supera este monto.")
    annex = fields.Selection([("1", "Anexo 1"), ("2", "Anexo 2 (bienes)"), ("3", "Anexo 3 (servicios)")],
                             string="Anexo", default="3")
    active = fields.Boolean(default=True)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s - %s (%s%%)" % (rec.code, rec.name, rec.rate)

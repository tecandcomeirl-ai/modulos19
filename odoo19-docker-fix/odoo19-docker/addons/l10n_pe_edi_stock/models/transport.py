from odoo import api, fields, models


class L10nPeVehicle(models.Model):
    _name = "l10n_pe.vehicle"
    _description = "Vehículo de transporte (GRE)"
    _rec_name = "plate"

    plate = fields.Char(string="Placa", required=True, size=8)
    brand = fields.Char(string="Marca / modelo")
    mtc_authorization = fields.Char(string="Autorización MTC / TUC")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("plate"):
                vals["plate"] = vals["plate"].replace("-", "").replace(" ", "").upper()
        return super().create(vals_list)


class L10nPeDriver(models.Model):
    _name = "l10n_pe.driver"
    _description = "Conductor (GRE)"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", string="Contacto")
    first_name = fields.Char(string="Nombres", required=True)
    last_name = fields.Char(string="Apellidos", required=True)
    doc_type = fields.Selection([("1", "DNI"), ("4", "Carnet de extranjería"), ("7", "Pasaporte")],
                                string="Tipo de documento", default="1", required=True)
    doc_number = fields.Char(string="N.º de documento", required=True)
    license = fields.Char(string="Licencia de conducir", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.depends("first_name", "last_name", "doc_number")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s %s (%s)" % (rec.first_name or "", rec.last_name or "", rec.doc_number or "")

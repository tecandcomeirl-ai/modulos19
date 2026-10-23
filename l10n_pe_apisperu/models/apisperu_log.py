from odoo import fields, models


class ApisPeruLog(models.Model):
    _name = "apisperu.log"
    _description = "Historial de consultas APIsPERU"
    _order = "id desc"

    date = fields.Datetime(default=fields.Datetime.now, readonly=True, index=True)
    company_id = fields.Many2one("res.company", readonly=True)
    user_id = fields.Many2one("res.users", string="Usuario", readonly=True)
    kind = fields.Selection([("dni", "DNI"), ("ruc", "RUC")], string="Tipo", readonly=True)
    masked_number = fields.Char(string="Número (enmascarado)", readonly=True,
                                help="Por privacidad no se guarda el documento completo ni los datos devueltos.")
    success = fields.Boolean(string="Correcta", readonly=True)
    error_code = fields.Char(string="Código de error", readonly=True)
    message = fields.Char(string="Mensaje", readonly=True)
    duration_ms = fields.Integer(string="Duración (ms)", readonly=True)

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sunat_detraction_account = fields.Char(
        string="Cuenta de detracciones (Banco de la Nación)", size=20,
        help="N.° de cuenta del proveedor en el Banco de la Nación. Se informa en el XML.")
    sunat_detraction_means = fields.Char(
        string="Medio de pago (Cat. 59)", default="001", size=3,
        help="001 = Depósito en cuenta.")
    sunat_detraction_round = fields.Boolean(
        string="Redondear detracción al sol", default=True,
        help="SUNAT redondea el depósito al entero más próximo (desde 0.50 sube). Verifique la norma vigente.")

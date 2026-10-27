from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sunat_api_client_id = fields.Char(
        string="Client ID (Consulta CPE)",
        help="SOL > Empresas > Comprobantes de Pago > Consulta de Validez de CPE > Credenciales de API SUNAT.")
    sunat_api_client_secret = fields.Char(string="Client Secret (Consulta CPE)")

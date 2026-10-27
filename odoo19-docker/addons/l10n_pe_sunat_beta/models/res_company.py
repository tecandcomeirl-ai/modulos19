from odoo import fields, models

SUNAT_URLS = {
    "beta": "https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/billService",
    "prod": "https://e-factura.sunat.gob.pe/ol-ti-itcpfegem/billService",
}


class ResCompany(models.Model):
    _inherit = "res.company"

    sunat_env = fields.Selection(
        [("beta", "Beta (pruebas)"), ("prod", "Producción")],
        string="Ambiente SUNAT", default="beta", required=True,
    )
    sunat_sol_user = fields.Char(
        string="Usuario SOL", default="MODDATOS",
        help="Beta: MODDATOS. Producción: usuario secundario SOL.",
    )
    sunat_sol_password = fields.Char(string="Clave SOL", default="moddatos",
                                     help="Beta: moddatos.")
    sunat_cert = fields.Binary(string="Certificado digital (.pfx/.p12)", attachment=True)
    sunat_cert_filename = fields.Char()
    sunat_cert_password = fields.Char(string="Clave del certificado")
    sunat_ubigeo = fields.Char(string="Ubigeo del emisor", size=6, default="150101")
    sunat_estab_code = fields.Char(
        string="Código de establecimiento", size=4, default="0000",
        help="Código de establecimiento anexo según SUNAT (0000 = domicilio fiscal).")

    def _sunat_endpoint(self):
        self.ensure_one()
        return SUNAT_URLS[self.sunat_env]

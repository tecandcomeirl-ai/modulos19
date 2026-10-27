from odoo import fields, models

GRE_PROD_AUTH = "https://api-seguridad.sunat.gob.pe"
GRE_PROD_API = "https://api-cpe.sunat.gob.pe"


class ResCompany(models.Model):
    _inherit = "res.company"

    sunat_gre_env = fields.Selection(
        [("test", "Pruebas (URL configurable)"), ("prod", "Producción SUNAT")],
        string="Ambiente GRE", default="test", required=True)
    sunat_gre_client_id = fields.Char(
        string="Client ID (API SUNAT)",
        help="Se genera en SOL > Empresas > Credenciales de API SUNAT.")
    sunat_gre_client_secret = fields.Char(string="Client Secret (API SUNAT)")
    sunat_gre_test_url = fields.Char(
        string="URL base de pruebas",
        default="https://gre-test.nubefact.com",
        help="SUNAT documenta un único ambiente (producción). Para pruebas puede apuntar a un "
             "sandbox compatible (ej. de un PSE/OSE). Verifique y cambie esta URL según su proveedor.")
    sunat_gre_series = fields.Char(string="Serie GRE remitente", default="T001", size=4)

    def _gre_urls(self):
        """(url_token, url_api) según ambiente."""
        self.ensure_one()
        if self.sunat_gre_env == "prod":
            token = "%s/v1/clientessol/%s/oauth2/token/" % (GRE_PROD_AUTH, self.sunat_gre_client_id)
            api = "%s/v1/contribuyente/gem/comprobantes/" % GRE_PROD_API
        else:
            base = (self.sunat_gre_test_url or "").rstrip("/")
            token = "%s/v1/clientessol/%s/oauth2/token/" % (base, self.sunat_gre_client_id)
            api = "%s/v1/contribuyente/gem/comprobantes/" % base
        return token, api

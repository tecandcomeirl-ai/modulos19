import re

from odoo import api, fields, models

SUNAT_TAX_CODES = [
    ("1000", "1000 - IGV (Impuesto General a las Ventas)"),
    ("1016", "1016 - IVAP (Arroz pilado)"),
    ("2000", "2000 - ISC (Impuesto Selectivo al Consumo)"),
    ("9995", "9995 - Exportación"),
    ("9997", "9997 - Exonerado"),
    ("9998", "9998 - Inafecto"),
    ("9999", "9999 - Otros tributos"),
]
SUNAT_AFECTACION = [
    ("10", "10 - Gravado, operación onerosa"),
    ("20", "20 - Exonerado, operación onerosa"),
    ("30", "30 - Inafecto, operación onerosa"),
    ("40", "40 - Exportación"),
]
DEFAULT_AFECT = {"1000": "10", "1016": "10", "2000": "10", "9995": "40",
                 "9997": "20", "9998": "30", "9999": "30"}


def sunat_guess_from_tax(name, amount):
    n = (name or "").upper()
    if re.search(r"\bISC\b", n):
        return "2000", "10"
    if re.search(r"\bIVAP\b", n):
        return "1016", "10"
    if "EXPORT" in n or re.search(r"\bEXP\b", n):
        return "9995", "40"
    if "EXON" in n or re.search(r"\bEXO\b", n):
        return "9997", "20"
    if "INAF" in n or re.search(r"\bINA\b", n):
        return "9998", "30"
    if "IGV" in n or abs((amount or 0.0) - 18.0) < 0.01:
        return "1000", "10"
    return False, False


class AccountTax(models.Model):
    _inherit = "account.tax"

    sunat_tax_code = fields.Selection(SUNAT_TAX_CODES, string="Tributo SUNAT (Cat. 05)")
    sunat_afectacion = fields.Selection(SUNAT_AFECTACION, string="Afectación IGV (Cat. 07)")

    @api.onchange("sunat_tax_code")
    def _onchange_sunat_tax_code(self):
        if self.sunat_tax_code and not self.sunat_afectacion:
            self.sunat_afectacion = DEFAULT_AFECT.get(self.sunat_tax_code)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("sunat_tax_code") and vals.get("type_tax_use") == "sale":
                code, afect = sunat_guess_from_tax(vals.get("name"), vals.get("amount"))
                if code:
                    vals["sunat_tax_code"], vals["sunat_afectacion"] = code, afect
        return super().create(vals_list)

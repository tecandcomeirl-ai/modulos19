from odoo import api, fields, models

# Catálogo 07 - afectación del IGV en operaciones NO onerosas (gratuitas)
FREE_AFECT = [
    ("11", "11 - Gravado: retiro por premio"),
    ("12", "12 - Gravado: retiro por donación"),
    ("13", "13 - Gravado: retiro"),
    ("14", "14 - Gravado: retiro por publicidad"),
    ("15", "15 - Gravado: bonificaciones"),
    ("16", "16 - Gravado: retiro por entrega a trabajadores"),
    ("21", "21 - Exonerado: transferencia gratuita"),
    ("31", "31 - Inafecto: retiro por bonificación"),
    ("32", "32 - Inafecto: retiro"),
    ("33", "33 - Inafecto: retiro por muestras médicas"),
    ("34", "34 - Inafecto: retiro por convenio colectivo"),
    ("35", "35 - Inafecto: retiro por premio"),
    ("36", "36 - Inafecto: retiro por publicidad"),
    ("37", "37 - Inafecto: transferencia gratuita"),
]
# familia de afectación -> tributo que debe tener la línea
FAMILY_TAX = {"1": "1000", "2": "9997", "3": "9998"}


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    sunat_free_afect = fields.Selection(
        FREE_AFECT, string="Operación gratuita", copy=True,
        help="Marque si la línea es una transferencia gratuita. El precio de la línea se toma como "
             "VALOR REFERENCIAL (sin IGV) y la línea se deja con descuento del 100 %.")
    sunat_free_unit_value = fields.Float(
        string="Valor referencial unitario", digits=(12, 10), compute="_compute_sunat_free_values")
    sunat_free_total = fields.Monetary(
        string="Valor referencial total", compute="_compute_sunat_free_values", currency_field="currency_id")
    sunat_free_tax = fields.Monetary(
        string="IGV teórico (no cobrado)", compute="_compute_sunat_free_values", currency_field="currency_id")

    @api.depends("sunat_free_afect", "price_unit", "quantity", "tax_ids", "currency_id", "product_id", "partner_id")
    def _compute_sunat_free_values(self):
        for line in self:
            total = tax = unit = 0.0
            if line.sunat_free_afect:
                res = line.tax_ids.compute_all(
                    line.price_unit, currency=line.currency_id, quantity=line.quantity,
                    product=line.product_id, partner=line.partner_id)
                total = res["total_excluded"]
                tax = res["total_included"] - res["total_excluded"]
                unit = total / line.quantity if line.quantity else 0.0
            line.sunat_free_unit_value = unit
            line.sunat_free_total = total
            line.sunat_free_tax = tax

    @api.onchange("sunat_free_afect")
    def _onchange_sunat_free_afect(self):
        for line in self:
            if line.sunat_free_afect:
                line.discount = 100.0
            elif line.discount == 100.0:
                line.discount = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("sunat_free_afect") and "discount" not in vals:
                vals["discount"] = 100.0
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("sunat_free_afect") and "discount" not in vals:
            vals = dict(vals, discount=100.0)
        return super().write(vals)

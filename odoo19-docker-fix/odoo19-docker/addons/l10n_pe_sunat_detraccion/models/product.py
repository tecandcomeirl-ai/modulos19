from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sunat_detraction_code_id = fields.Many2one(
        "sunat.detraction.code", string="Detracción (SPOT)",
        help="Si el producto/servicio está sujeto a detracción, la factura la calcula sola.")

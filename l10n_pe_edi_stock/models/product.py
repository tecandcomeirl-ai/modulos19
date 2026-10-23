from odoo import fields, models

# Tabla 5 del PLE - Tipo de existencia
EXISTENCE_TYPES = [
    ("01", "01 - Mercadería"),
    ("02", "02 - Producto terminado"),
    ("03", "03 - Materias primas y auxiliares - Materiales"),
    ("04", "04 - Envases y embalajes"),
    ("05", "05 - Suministros diversos"),
    ("91", "91 - Otros 1"),
    ("92", "92 - Otros 2"),
    ("99", "99 - Otros 5"),
]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sunat_existence_type = fields.Selection(
        EXISTENCE_TYPES, string="Tipo de existencia (PLE)", default="01",
        help="Tabla 5 del PLE. Se usa en los registros de inventario permanente.")
    sunat_unspsc_code = fields.Char(
        string="Código UNSPSC / GTIN", help="Opcional. Se informa si figura en el comprobante electrónico.")

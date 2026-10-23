from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ple_sire = fields.Boolean(
        string="Empresa incorporada al SIRE",
        default=True,
        help="Si está marcada, los registros de ventas y compras se presentan en el SIRE: "
             "el PLE 14.1/8.1 queda como respaldo y el campo 20 (Dato estructurado) del Libro Diario "
             "se deja vacío.")

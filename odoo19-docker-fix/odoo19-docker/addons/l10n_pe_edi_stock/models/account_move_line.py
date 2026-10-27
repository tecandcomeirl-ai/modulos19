from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    sunat_uom_code = fields.Char(related="product_uom_id.sunat_uom_code", string="Unidad SUNAT")

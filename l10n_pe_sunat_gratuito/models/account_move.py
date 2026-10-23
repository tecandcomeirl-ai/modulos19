from odoo import _, models
from odoo.exceptions import UserError

from .account_move_line import FAMILY_TAX


class AccountMove(models.Model):
    _inherit = "account.move"

    def _sunat_check_before_send(self):
        super()._sunat_check_before_send()
        for move in self:
            for line in move.invoice_line_ids.filtered(
                    lambda l: l.display_type == "product" and l.sunat_free_afect):
                label = line.name or line.product_id.display_name
                if line.discount != 100.0:
                    raise UserError(_("Línea gratuita «%s»: debe tener 100 %% de descuento "
                                      "(el precio es solo el valor referencial).", label))
                if line.price_unit <= 0:
                    raise UserError(_("Línea gratuita «%s»: indique el valor referencial "
                                      "(precio unitario mayor a cero).", label))
                needed = FAMILY_TAX[line.sunat_free_afect[0]]
                codes = [getattr(t, "sunat_tax_code", False) for t in line.tax_ids]
                if needed not in codes:
                    raise UserError(_(
                        "Línea gratuita «%(line)s»: la afectación %(afect)s requiere un impuesto con "
                        "Tributo SUNAT %(tax)s.", line=label, afect=line.sunat_free_afect, tax=needed))

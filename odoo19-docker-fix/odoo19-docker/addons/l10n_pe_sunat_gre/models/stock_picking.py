from odoo import Command, _, fields, models
from odoo.exceptions import UserError

from .sunat_gre import UOM_MAP, partner_doc_type, partner_ubigeo


class StockPicking(models.Model):
    _inherit = "stock.picking"

    sunat_gre_ids = fields.One2many("sunat.gre", "picking_id", string="GRE SUNAT")
    sunat_gre_count = fields.Integer(compute="_compute_sunat_gre_count")

    def _compute_sunat_gre_count(self):
        for picking in self:
            picking.sunat_gre_count = len(picking.sunat_gre_ids)

    def _prepare_sunat_gre_vals(self):
        """Valores para crear la GRE desde la operación (extensible por otros módulos)."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Indique el contacto de destino en la operación."))
        company = self.company_id
        origin_partner = self.picking_type_id.warehouse_id.partner_id or company.partner_id
        lines, weight = [], 0.0
        for move in self.move_ids:
            qty = move.quantity or move.product_uom_qty
            if not qty:
                continue
            weight += (move.product_id.weight or 0.0) * qty
            lines.append(Command.create({
                "product_id": move.product_id.id,
                "product_code": move.product_id.default_code,
                "description": move.product_id.display_name,
                "quantity": qty,
                "uom_code": UOM_MAP.get((move.product_uom.name or "").lower(), "NIU"),
            }))
        partner = self.partner_id
        return {
            "company_id": company.id,
            "picking_id": self.id,
            "partner_id": partner.id,
            "partner_vat": partner.vat,
            "partner_doc_type": partner_doc_type(partner),
            "reason": "04" if self.picking_type_code == "internal" else "01",
            "gross_weight": weight,
            "origin_ubigeo": partner_ubigeo(origin_partner) or company.sunat_ubigeo,
            "origin_address": origin_partner.street or "",
            "dest_ubigeo": partner_ubigeo(partner),
            "dest_address": partner.street or "",
            "line_ids": lines,
        }

    def action_create_sunat_gre(self):
        self.ensure_one()
        gre = self.env["sunat.gre"].create(self._prepare_sunat_gre_vals())
        return {
            "type": "ir.actions.act_window", "res_model": "sunat.gre",
            "res_id": gre.id, "view_mode": "form", "target": "current",
        }

    def action_view_sunat_gre(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("GRE SUNAT"),
            "res_model": "sunat.gre", "view_mode": "list,form",
            "domain": [("picking_id", "=", self.id)],
        }

# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, release

V = release.version_info[0]


class AccountAccount(models.Model):
    _inherit = "account.account"

    acc_asset_category_id = fields.Many2one(
        "acc.asset.category", string="Asset / Deferral Category",
        help="Bills and invoices posted on this account automatically create an asset or deferral of this category.")


class AccountMove(models.Model):
    _inherit = "account.move"

    acc_asset_id = fields.Many2one("acc.asset", string="Asset", index=True, copy=False, ondelete="set null")
    acc_created_asset_ids = fields.One2many("acc.asset", "source_move_id", string="Created Assets")
    acc_created_asset_count = fields.Integer(compute="_compute_acc_created_asset_count")

    def _compute_acc_created_asset_count(self):
        for move in self:
            move.acc_created_asset_count = len(move.acc_created_asset_ids)

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted._acc_create_assets()
        return posted

    def _acc_create_assets(self):
        Asset = self.env["acc.asset"]
        for move in self:
            if move.move_type not in ("in_invoice", "out_invoice") or move.acc_created_asset_ids:
                continue
            for line in move.invoice_line_ids:
                cat = line.account_id.acc_asset_category_id
                if not cat or not cat.auto_create or move.company_id.currency_id.is_zero(line.balance):
                    continue
                if cat.asset_type == "revenue" and move.move_type != "out_invoice":
                    continue
                if cat.asset_type != "revenue" and move.move_type != "in_invoice":
                    continue
                asset = Asset.create({
                    "name": line.name or (line.product_id and line.product_id.display_name) or move.name,
                    "code": move.name,
                    "category_id": cat.id,
                    "company_id": move.company_id.id,
                    "partner_id": move.partner_id.id,
                    "date": move.invoice_date or move.date,
                    "value": abs(line.balance),
                    "source_move_id": move.id,
                })
                asset.message_post(body=_("Created from %s") % move.name)
                if cat.auto_confirm:
                    asset.action_confirm()

    def button_draft(self):
        res = super().button_draft()
        self.mapped("acc_created_asset_ids").filtered(lambda a: a.state == "draft").unlink()
        return res

    def action_view_acc_assets(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Assets"), "res_model": "acc.asset",
                "views": [(False, "form")] if len(self.acc_created_asset_ids) == 1 else [(False, "tree" if V in (16, 17) else "list"), (False, "form")],
                "res_id": self.acc_created_asset_ids[:1].id, "domain": [("id", "in", self.acc_created_asset_ids.ids)]}

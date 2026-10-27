# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccAssetDispose(models.TransientModel):
    _name = "acc.asset.dispose"
    _description = "Dispose / Sell Asset"

    asset_id = fields.Many2one("acc.asset", required=True)
    currency_id = fields.Many2one(related="asset_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    action = fields.Selection([("dispose", "Dispose (scrap / write off)"), ("sell", "Sell")], required=True, default="dispose")
    sale_value = fields.Monetary(string="Sale Proceeds")
    proceeds_account_id = fields.Many2one("account.account", string="Proceeds Account",
                                          help="Receivable, bank or clearing account that receives the sale proceeds.")
    gain_account_id = fields.Many2one("account.account", string="Gain Account")
    loss_account_id = fields.Many2one("account.account", string="Loss Account")
    post_depreciation = fields.Boolean(string="Post Due Depreciation First", default=True)

    def action_confirm(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.asset_type != "asset" or asset.state != "open":
            raise UserError(_("Only running fixed assets can be disposed of."))
        if self.post_depreciation:
            asset.action_post_due(self.date)
        if asset.state != "open" and asset.state != "close":
            raise UserError(_("The asset is not running."))
        cat = asset.category_id
        cur = asset.currency_id
        draft_moves = asset.line_ids.mapped("move_id").filtered(lambda m: m.state == "draft")
        draft_moves.unlink()
        asset.line_ids.filtered(lambda l: not l.move_id).unlink()
        accumulated = asset.already_depreciated + sum(asset.line_ids.filtered(lambda l: l.move_id).mapped("amount"))
        proceeds = self.sale_value if self.action == "sell" else 0.0
        diff = cur.round(asset.value - accumulated - proceeds)  # > 0 loss, < 0 gain
        lines = [(0, 0, {"name": _("%s: gross value") % asset.name, "account_id": cat.account_asset_id.id, "debit": 0.0, "credit": asset.value})]
        if not cur.is_zero(accumulated):
            lines.append((0, 0, {"name": _("%s: accumulated depreciation") % asset.name, "account_id": cat.account_depreciation_id.id, "debit": accumulated, "credit": 0.0}))
        if not cur.is_zero(proceeds):
            if not self.proceeds_account_id:
                raise UserError(_("Select the proceeds account."))
            lines.append((0, 0, {"name": _("%s: sale proceeds") % asset.name, "account_id": self.proceeds_account_id.id, "debit": proceeds, "credit": 0.0, "partner_id": asset.partner_id.id or False}))
        if not cur.is_zero(diff):
            acc = self.loss_account_id if diff > 0 else self.gain_account_id
            if not acc:
                acc = cat.account_expense_id
            lines.append((0, 0, {"name": _("%s: loss on disposal") % asset.name if diff > 0 else _("%s: gain on disposal") % asset.name,
                                 "account_id": acc.id, "debit": diff if diff > 0 else 0.0, "credit": -diff if diff < 0 else 0.0}))
        move = self.env["account.move"].create({
            "move_type": "entry", "journal_id": cat.journal_id.id, "date": self.date,
            "ref": _("Disposal of %s") % asset.name, "acc_asset_id": asset.id, "line_ids": lines,
        })
        move._post()
        asset.write({"state": "close", "disposal_date": self.date})
        asset.message_post(body=_("Asset disposed on %s (%s).") % (self.date, move.name))
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": move.id, "views": [(False, "form")]}

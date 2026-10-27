# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, release
from odoo.exceptions import UserError

V = release.version_info[0]

LOCK_FIELDS = ["fiscalyear_lock_date", "tax_lock_date", "sale_lock_date", "purchase_lock_date", "hard_lock_date"]


class AccLockDate(models.TransientModel):
    _name = "acc.lock.date"
    _description = "Accounting Lock Dates"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, readonly=True)
    fiscalyear_lock_date = fields.Date(string="Lock Date for All Users",
                                       help="Nobody can post or edit entries on or before this date (year end closing).")
    tax_lock_date = fields.Date(string="Tax Lock Date", help="No entry with taxes on or before this date (VAT return filed).")
    sale_lock_date = fields.Date(string="Sales Lock Date", help="No sales documents on or before this date.")
    purchase_lock_date = fields.Date(string="Purchase Lock Date", help="No purchase documents on or before this date.")
    hard_lock_date = fields.Date(string="Hard Lock Date", help="Irreversible: cannot be removed or moved back once set.")
    draft_count = fields.Integer(compute="_compute_draft_count", string="Draft Entries Before Lock")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        for f in LOCK_FIELDS:
            if f in fields_list:
                res[f] = company[f]
        return res

    @api.depends(*LOCK_FIELDS)
    def _compute_draft_count(self):
        for w in self:
            dates = [w[f] for f in LOCK_FIELDS if w[f]]
            if not dates:
                w.draft_count = 0
                continue
            w.draft_count = self.env["account.move"].search_count([("company_id", "=", w.company_id.id), ("state", "=", "draft"), ("date", "<=", max(dates))])

    def action_open_drafts(self):
        self.ensure_one()
        dates = [self[f] for f in LOCK_FIELDS if self[f]]
        return {"type": "ir.actions.act_window", "name": _("Draft Entries"), "res_model": "account.move",
                "views": self.env["acc.report.engine"]._views_for("account.move"),
                "domain": [("company_id", "=", self.company_id.id), ("state", "=", "draft"), ("date", "<=", max(dates) if dates else False)]}

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only accounting managers can change lock dates."))
        vals = {f: self[f] for f in LOCK_FIELDS if self[f] != self.company_id[f]}
        if vals:
            self.company_id.sudo().write(vals)
            self.company_id.message_post(body=_("Lock dates changed by %s: %s") % (self.env.user.name, ", ".join("%s = %s" % (k, v or "-") for k, v in vals.items()))) \
                if hasattr(self.company_id, "message_post") else None
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Lock dates"), "message": _("Lock dates saved."), "type": "success", "next": {"type": "ir.actions.act_window_close"}}}

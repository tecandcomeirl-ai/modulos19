# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, release
from odoo.exceptions import UserError, ValidationError

V = release.version_info[0]


class AccRecurringEntry(models.Model):
    _name = "acc.recurring.entry"
    _description = "Recurring Journal Entry"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_date, id"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Number", readonly=True, copy=False, default="/")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    journal_id = fields.Many2one("account.journal", required=True, domain=[("type", "=", "general")], tracking=True)
    partner_id = fields.Many2one("res.partner")
    ref = fields.Char(string="Entry Reference")
    date_start = fields.Date(string="First Date", required=True, default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(string="End Date", tracking=True)
    interval_number = fields.Integer(string="Repeat Every", default=1, required=True)
    interval_type = fields.Selection([("days", "Days"), ("weeks", "Weeks"), ("months", "Months"), ("years", "Years")],
                                     default="months", required=True)
    next_date = fields.Date(string="Next Date", copy=False, tracking=True)
    auto_post = fields.Boolean(string="Post Automatically", default=True)
    state = fields.Selection([("draft", "Draft"), ("running", "Running"), ("done", "Finished"), ("stopped", "Stopped")],
                             default="draft", required=True, copy=False, tracking=True)
    line_ids = fields.One2many("acc.recurring.entry.line", "entry_id", string="Lines", copy=True)
    move_ids = fields.One2many("account.move", "acc_recurring_id", string="Generated Entries", copy=False)
    move_count = fields.Integer(compute="_compute_move_count")
    total_debit = fields.Monetary(compute="_compute_totals")
    total_credit = fields.Monetary(compute="_compute_totals")

    @api.depends("line_ids.debit", "line_ids.credit")
    def _compute_totals(self):
        for r in self:
            r.total_debit = sum(r.line_ids.mapped("debit"))
            r.total_credit = sum(r.line_ids.mapped("credit"))

    def _compute_move_count(self):
        for r in self:
            r.move_count = len(r.move_ids)

    @api.constrains("interval_number")
    def _check_interval(self):
        if any(r.interval_number <= 0 for r in self):
            raise ValidationError(_("The interval must be positive."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "/") == "/":
                vals["code"] = self.env["ir.sequence"].next_by_code("acc.recurring.entry") or "/"
        return super().create(vals_list)

    def _delta(self):
        return relativedelta(**{self.interval_type: self.interval_number})

    def action_start(self):
        for r in self:
            if not r.line_ids:
                raise UserError(_("Add the journal entry lines first."))
            if r.currency_id.compare_amounts(r.total_debit, r.total_credit) != 0:
                raise UserError(_("The entry is not balanced: debit %s, credit %s.") % (r.total_debit, r.total_credit))
            r.write({"state": "running", "next_date": r.next_date or r.date_start})
        return True

    def action_stop(self):
        self.write({"state": "stopped"})

    def action_draft(self):
        self.write({"state": "draft"})

    def _prepare_move(self, day):
        self.ensure_one()
        return {
            "move_type": "entry", "journal_id": self.journal_id.id, "date": day, "ref": self.ref or self.name,
            "acc_recurring_id": self.id, "company_id": self.company_id.id,
            "line_ids": [(0, 0, {"name": l.name or self.name, "account_id": l.account_id.id, "partner_id": (l.partner_id or self.partner_id).id or False,
                                 "debit": l.debit, "credit": l.credit}) for l in self.line_ids],
        }

    def action_generate(self, up_to=None):
        up_to = up_to or fields.Date.context_today(self)
        moves = self.env["account.move"]
        for r in self.filtered(lambda x: x.state == "running"):
            guard = 0
            while r.next_date and r.next_date <= up_to and guard < 400:
                if r.date_end and r.next_date > r.date_end:
                    r.state = "done"
                    break
                move = self.env["account.move"].create(r._prepare_move(r.next_date))
                if r.auto_post:
                    move._post()
                moves |= move
                # step from the first date so month ends stay month ends (31 Jan, 28 Feb, 31 Mar...)
                r.next_date = r.date_start + relativedelta(**{r.interval_type: r.interval_number * len(r.move_ids)})
                guard += 1
            if r.date_end and r.next_date and r.next_date > r.date_end:
                r.state = "done"
        return moves

    def action_generate_now(self):
        moves = self.action_generate()
        if not moves:
            raise UserError(_("Nothing to generate: the next date is in the future."))
        return self.action_view_moves()

    @api.model
    def _cron_generate(self):
        self.search([("state", "=", "running")]).action_generate()

    def action_view_moves(self):
        return {"type": "ir.actions.act_window", "name": _("Generated Entries"), "res_model": "account.move",
                "views": self.env["acc.report.engine"]._views_for("account.move"), "domain": [("acc_recurring_id", "in", self.ids)],
                "context": {"create": False}}


class AccRecurringEntryLine(models.Model):
    _name = "acc.recurring.entry.line"
    _description = "Recurring Entry Line"
    _order = "entry_id, sequence, id"

    entry_id = fields.Many2one("acc.recurring.entry", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    account_id = fields.Many2one("account.account", required=True)
    partner_id = fields.Many2one("res.partner")
    name = fields.Char(string="Label")
    currency_id = fields.Many2one(related="entry_id.currency_id")
    debit = fields.Monetary()
    credit = fields.Monetary()


class AccountMove(models.Model):
    _inherit = "account.move"

    acc_recurring_id = fields.Many2one("acc.recurring.entry", string="Recurring Entry", index=True, copy=False, ondelete="set null")
    acc_pdc_id = fields.Many2one("acc.pdc", string="Post Dated Cheque", index=True, copy=False, ondelete="set null")

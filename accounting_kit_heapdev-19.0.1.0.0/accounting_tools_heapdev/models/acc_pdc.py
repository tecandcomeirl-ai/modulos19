# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, release
from odoo.exceptions import UserError

V = release.version_info[0]


class AccPdc(models.Model):
    _name = "acc.pdc"
    _description = "Post Dated Cheque"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "cheque_date, id"

    name = fields.Char(string="Number", readonly=True, copy=False, default="/")
    pdc_type = fields.Selection([("receive", "Received"), ("issue", "Issued")], required=True, default="receive", tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    amount = fields.Monetary(required=True, tracking=True)
    cheque_number = fields.Char(required=True, tracking=True)
    bank_name = fields.Char(string="Drawn On (Bank)")
    date = fields.Date(string="Received / Issued On", required=True, default=fields.Date.context_today)
    cheque_date = fields.Date(string="Cheque Date (Maturity)", required=True, tracking=True)
    journal_id = fields.Many2one("account.journal", string="Bank Journal", required=True, domain=[("type", "=", "bank")],
                                 default=lambda self: self.env["account.journal"].search([("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1))
    misc_journal_id = fields.Many2one("account.journal", string="PDC Journal", required=True, domain=[("type", "=", "general")],
                                      default=lambda self: self.env["account.journal"].search([("type", "=", "general"), ("company_id", "=", self.env.company.id)], limit=1))
    pdc_account_id = fields.Many2one("account.account", string="PDC Account", required=True,
                                     default=lambda self: self._default_pdc_account())
    invoice_ids = fields.Many2many("account.move", "acc_pdc_invoice_rel", "pdc_id", "move_id", string="Invoices / Bills",
                                   help="Open invoices or bills settled by this cheque.")
    memo = fields.Char()
    state = fields.Selection([("draft", "Draft"), ("registered", "Registered"), ("deposited", "Deposited"),
                              ("cleared", "Cleared"), ("bounced", "Bounced"), ("cancel", "Cancelled")],
                             default="draft", required=True, copy=False, tracking=True)
    move_ids = fields.One2many("account.move", "acc_pdc_id", string="Entries", copy=False)
    register_move_id = fields.Many2one("account.move", readonly=True, copy=False)
    clear_move_id = fields.Many2one("account.move", readonly=True, copy=False)
    bounce_move_id = fields.Many2one("account.move", readonly=True, copy=False)
    days_to_maturity = fields.Integer(compute="_compute_days")

    @api.model
    def _default_pdc_account(self):
        kind = self.env.context.get("default_pdc_type", "receive")
        company = self.env.company
        return (company.acc_pdc_receivable_account_id if kind == "receive" else company.acc_pdc_payable_account_id).id

    @api.onchange("pdc_type")
    def _onchange_pdc_type(self):
        company = self.company_id or self.env.company
        acc = company.acc_pdc_receivable_account_id if self.pdc_type == "receive" else company.acc_pdc_payable_account_id
        if acc:
            self.pdc_account_id = acc

    @api.onchange("invoice_ids")
    def _onchange_invoices(self):
        if self.invoice_ids and not self.amount:
            self.amount = sum(self.invoice_ids.mapped("amount_residual"))

    def _compute_days(self):
        today = fields.Date.context_today(self)
        for r in self:
            r.days_to_maturity = (r.cheque_date - today).days if r.cheque_date else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("acc.pdc") or "/"
        return super().create(vals_list)

    def _partner_account(self):
        p = self.partner_id.commercial_partner_id.with_company(self.company_id)
        return p.property_account_receivable_id if self.pdc_type == "receive" else p.property_account_payable_id

    def _make_move(self, day, debit_acc, credit_acc, label, journal=None):
        partner = self.partner_id.commercial_partner_id.id
        move = self.env["account.move"].create({
            "move_type": "entry", "journal_id": (journal or self.misc_journal_id).id, "date": day, "ref": "%s %s" % (self.name, label),
            "acc_pdc_id": self.id,
            "line_ids": [(0, 0, {"name": "%s - %s %s" % (label, _("Cheque"), self.cheque_number), "account_id": debit_acc.id, "partner_id": partner,
                                 "debit": self.amount, "credit": 0.0}),
                         (0, 0, {"name": "%s - %s %s" % (label, _("Cheque"), self.cheque_number), "account_id": credit_acc.id, "partner_id": partner,
                                 "debit": 0.0, "credit": self.amount})],
        })
        move._post()
        return move

    def action_register(self):
        for r in self:
            if r.state != "draft":
                continue
            if r.amount <= 0:
                raise UserError(_("The cheque amount must be positive."))
            if not r.pdc_account_id.reconcile:
                raise UserError(_("The PDC account %s must allow reconciliation.") % r.pdc_account_id.display_name)
            partner_acc = r._partner_account()
            if r.pdc_type == "receive":
                move = r._make_move(r.date, r.pdc_account_id, partner_acc, _("PDC received"))
            else:
                move = r._make_move(r.date, partner_acc, r.pdc_account_id, _("PDC issued"))
            r.write({"register_move_id": move.id, "state": "registered"})
            if r.invoice_ids:
                line = move.line_ids.filtered(lambda l: l.account_id == partner_acc)
                inv_lines = r.invoice_ids.mapped("line_ids").filtered(lambda l: l.account_id == partner_acc and not l.reconciled)
                if inv_lines:
                    (line | inv_lines).reconcile()
        return True

    def action_deposit(self):
        self.filtered(lambda r: r.state == "registered" and r.pdc_type == "receive").write({"state": "deposited"})
        return True

    def action_clear(self):
        today = fields.Date.context_today(self)
        for r in self:
            if r.state not in ("registered", "deposited"):
                continue
            bank_acc = r.journal_id.default_account_id
            day = min(r.cheque_date, today) if r.cheque_date else today
            if r.pdc_type == "receive":
                move = r._make_move(day, bank_acc, r.pdc_account_id, _("PDC cleared"), r.journal_id)
            else:
                move = r._make_move(day, r.pdc_account_id, bank_acc, _("PDC presented"), r.journal_id)
            r.write({"clear_move_id": move.id, "state": "cleared"})
            r._reconcile_pdc_lines()
        return True

    def action_bounce(self):
        today = fields.Date.context_today(self)
        for r in self:
            if r.state not in ("registered", "deposited"):
                continue
            partner_acc = r._partner_account()
            reg_line = r.register_move_id.line_ids.filtered(lambda l: l.account_id == partner_acc)
            if reg_line.matched_debit_ids or reg_line.matched_credit_ids:
                reg_line.remove_move_reconcile()
            if r.pdc_type == "receive":
                move = r._make_move(today, partner_acc, r.pdc_account_id, _("PDC bounced"))
            else:
                move = r._make_move(today, r.pdc_account_id, partner_acc, _("PDC cancelled"))
            r.write({"bounce_move_id": move.id, "state": "bounced"})
            back = move.line_ids.filtered(lambda l: l.account_id == partner_acc)
            (back | reg_line).reconcile()
            r._reconcile_pdc_lines()
            r.message_post(body=_("Cheque %s bounced; the customer balance and the invoices are open again.") % r.cheque_number)
        return True

    def _reconcile_pdc_lines(self):
        for r in self:
            lines = r.move_ids.mapped("line_ids").filtered(lambda l: l.account_id == r.pdc_account_id and not l.reconciled)
            if len(lines) > 1 and r.currency_id.is_zero(sum(lines.mapped("balance"))):
                lines.reconcile()

    def action_cancel(self):
        for r in self:
            if r.state != "draft":
                raise UserError(_("Only draft cheques can be cancelled; bounce registered cheques instead."))
            r.state = "cancel"
        return True

    def action_draft(self):
        self.filtered(lambda r: r.state == "cancel").write({"state": "draft"})
        return True

    def action_view_moves(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Entries"), "res_model": "account.move",
                "views": self.env["acc.report.engine"]._views_for("account.move"), "domain": [("id", "in", self.move_ids.ids)]}

    def unlink(self):
        if self.filtered(lambda r: r.state not in ("draft", "cancel")):
            raise UserError(_("Only draft or cancelled cheques can be deleted."))
        return super().unlink()

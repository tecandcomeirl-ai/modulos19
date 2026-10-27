# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class PettyCashBook(models.Model):
    _name = "petty.cash.book"
    _description = "Petty Cash Book"
    _order = "name"

    name = fields.Char(required=True, default=lambda self: _("Petty Cash"))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        "res.currency", required=True,
        default=lambda self: self.env.company.currency_id)
    responsible_id = fields.Many2one(
        "res.users", string="Responsible", default=lambda self: self.env.user)
    opening_balance = fields.Monetary(help="Cash in the box before the first transaction.")
    line_ids = fields.One2many("petty.cash.line", "book_id", string="Transactions")

    total_in = fields.Monetary(compute="_compute_balances", string="Total In")
    total_out = fields.Monetary(compute="_compute_balances", string="Total Out")
    balance = fields.Monetary(compute="_compute_balances", string="Balance on Hand")
    line_count = fields.Integer(compute="_compute_balances")

    @api.depends("opening_balance", "line_ids.amount", "line_ids.line_type")
    def _compute_balances(self):
        for book in self:
            lines = book.line_ids
            total_in = sum(lines.filtered(lambda l: l.line_type == "in").mapped("amount"))
            total_out = sum(lines.filtered(lambda l: l.line_type == "out").mapped("amount"))
            book.total_in = total_in
            book.total_out = total_out
            book.balance = book.opening_balance + total_in - total_out
            book.line_count = len(lines)


class PettyCashLine(models.Model):
    _name = "petty.cash.line"
    _description = "Petty Cash Transaction"
    _order = "date, id"

    book_id = fields.Many2one(
        "petty.cash.book", string="Cash Book", required=True,
        ondelete="cascade", index=True)
    company_id = fields.Many2one(related="book_id.company_id", store=True)
    currency_id = fields.Many2one(related="book_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    name = fields.Char(string="Description", required=True)
    ref = fields.Char(string="Reference")
    payee = fields.Char(string="Paid To / Received From")
    line_type = fields.Selection(
        [("in", "Cash In"), ("out", "Cash Out")],
        string="Type", required=True, default="out")
    amount = fields.Monetary(required=True)
    signed_amount = fields.Monetary(
        compute="_compute_signed_amount", string="Signed Amount", store=True)

    @api.depends("amount", "line_type")
    def _compute_signed_amount(self):
        for line in self:
            line.signed_amount = line.amount if line.line_type == "in" else -line.amount

    @api.constrains("amount")
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("The amount must be greater than zero."))

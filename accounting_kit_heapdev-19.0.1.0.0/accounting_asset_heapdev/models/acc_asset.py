# -*- coding: utf-8 -*-
import calendar
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, release
from odoo.exceptions import UserError, ValidationError

V = release.version_info[0]

ASSET_TYPES = [("asset", "Fixed Asset"), ("expense", "Deferred Expense"), ("revenue", "Deferred Revenue")]

def _acc_flush(env):
    """Write pending ORM changes to the database before raw SQL (Odoo 16+ no longer flushes on cr.execute)."""
    if hasattr(env, "flush_all"):
        env.flush_all()
    else:
        env["base"].flush()

class AccAssetCategory(models.Model):
    _name = "acc.asset.category"
    _description = "Asset / Deferral Category"
    _order = "asset_type, name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    asset_type = fields.Selection(ASSET_TYPES, string="Type", required=True, default="asset")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    journal_id = fields.Many2one("account.journal", string="Journal", required=True, domain=[("type", "=", "general")])
    account_asset_id = fields.Many2one("account.account", string="Asset / Deferral Account", required=True,
                                       help="Account the purchase (or the deferred income / prepaid expense) is booked on. "
                                            "Bills and invoices posted on this account create an asset automatically.")
    account_depreciation_id = fields.Many2one("account.account", string="Depreciation / Deferral Account", required=True,
                                              help="Accumulated depreciation for assets; the deferral account (usually the same "
                                                   "as the asset account) for deferred revenue and expense.")
    account_expense_id = fields.Many2one("account.account", string="Expense / Income Account", required=True,
                                         help="Depreciation expense for assets, the expense account for deferred expenses "
                                              "or the income account for deferred revenue.")
    method = fields.Selection([("linear", "Straight Line (Linear)"), ("degressive", "Declining Balance (Degressive)")],
                              required=True, default="linear")
    method_number = fields.Integer(string="Number of Periods", required=True, default=60)
    method_period = fields.Integer(string="Period Length (months)", required=True, default=1)
    degressive_factor = fields.Float(string="Declining Factor", default=2.0,
                                     help="2.0 = double declining balance. The method switches to linear when that gives more.")
    prorata = fields.Boolean(string="Prorata Temporis", default=True,
                             help="First period is computed on the number of days from the start date.")
    auto_post = fields.Boolean(string="Post Entries Automatically", default=True)
    auto_create = fields.Boolean(string="Create from Bills / Invoices", default=True)
    auto_confirm = fields.Boolean(string="Confirm Automatically", default=False,
                                  help="Assets created from bills and invoices are confirmed right away.")
    asset_count = fields.Integer(compute="_compute_asset_count")

    def _compute_asset_count(self):
        data = {}
        if self.ids:
            _acc_flush(self.env)
            self.env.cr.execute("SELECT category_id, count(*) FROM acc_asset WHERE category_id = ANY(%s) GROUP BY category_id", [self.ids])
            data = dict(self.env.cr.fetchall())
        for cat in self:
            cat.asset_count = data.get(cat.id, 0)

    @api.onchange("asset_type", "account_asset_id")
    def _onchange_type(self):
        if self.asset_type in ("expense", "revenue") and self.account_asset_id:
            self.account_depreciation_id = self.account_asset_id
        if self.asset_type != "asset":
            self.method = "linear"
            if self.method_number == 60:
                self.method_number = 12

    @api.constrains("method_number", "method_period")
    def _check_numbers(self):
        for cat in self:
            if cat.method_number <= 0 or cat.method_period <= 0:
                raise ValidationError(_("The number of periods and the period length must be positive."))

    def action_view_assets(self):
        self.ensure_one()
        action = self.env["acc.asset"]._action_for_type(self.asset_type)
        action["domain"] = [("category_id", "=", self.id)]
        action["context"] = {"default_category_id": self.id}
        return action


class AccAsset(models.Model):
    _name = "acc.asset"
    _description = "Asset / Deferred Revenue / Deferred Expense"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Reference")
    asset_type = fields.Selection(ASSET_TYPES, string="Type", required=True, default=lambda self: self.env.context.get("default_asset_type", "asset"))
    category_id = fields.Many2one("acc.asset.category", string="Category", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", string="Currency")
    partner_id = fields.Many2one("res.partner", string="Partner")
    state = fields.Selection([("draft", "Draft"), ("open", "Running"), ("close", "Closed"), ("cancel", "Cancelled")],
                             default="draft", required=True, copy=False, tracking=True)
    date = fields.Date(string="Acquisition Date", required=True, default=fields.Date.context_today, tracking=True)
    first_depreciation_date = fields.Date(string="First Depreciation Date",
                                          help="Leave empty to use the end of the first period.")
    value = fields.Monetary(string="Gross Value", required=True, tracking=True)
    salvage_value = fields.Monetary(string="Salvage Value", tracking=True)
    already_depreciated = fields.Monetary(string="Depreciation Before Import",
                                          help="Depreciation already booked outside Odoo (opening balance), not posted again.")
    method = fields.Selection([("linear", "Straight Line (Linear)"), ("degressive", "Declining Balance (Degressive)")], required=True, default="linear")
    method_number = fields.Integer(string="Number of Periods", required=True, default=60)
    method_period = fields.Integer(string="Period Length (months)", required=True, default=1)
    degressive_factor = fields.Float(string="Declining Factor", default=2.0)
    prorata = fields.Boolean(string="Prorata Temporis", default=True)
    auto_post = fields.Boolean(string="Post Entries Automatically", default=True)
    line_ids = fields.One2many("acc.asset.line", "asset_id", string="Depreciation Board", copy=False)
    move_ids = fields.One2many("account.move", "acc_asset_id", string="Entries", copy=False)
    source_move_id = fields.Many2one("account.move", string="Source Document", copy=False, readonly=True)
    value_residual = fields.Monetary(string="Residual Value", compute="_compute_values", store=True)
    depreciated_value = fields.Monetary(string="Depreciated", compute="_compute_values", store=True)
    book_value = fields.Monetary(string="Book Value", compute="_compute_values", store=True)
    entry_count = fields.Integer(compute="_compute_entry_count")
    disposal_date = fields.Date(readonly=True, copy=False)
    note = fields.Text()

    @api.depends("value", "salvage_value", "already_depreciated", "line_ids.move_id", "line_ids.amount", "line_ids.move_id.state", "state")
    def _compute_values(self):
        for asset in self:
            done = sum(l.amount for l in asset.line_ids if l.move_id and l.move_id.state == "posted")
            asset.depreciated_value = done + asset.already_depreciated
            asset.value_residual = asset.value - asset.salvage_value - asset.depreciated_value
            asset.book_value = asset.value - asset.depreciated_value if asset.state != "close" or not asset.disposal_date else 0.0

    def _compute_entry_count(self):
        for asset in self:
            asset.entry_count = len(asset.move_ids)

    @api.onchange("category_id")
    def _onchange_category(self):
        cat = self.category_id
        if cat:
            self.asset_type = cat.asset_type
            self.method = cat.method
            self.method_number = cat.method_number
            self.method_period = cat.method_period
            self.degressive_factor = cat.degressive_factor
            self.prorata = cat.prorata
            self.auto_post = cat.auto_post

    @api.model
    def _vals_from_category(self, cat):
        return {"asset_type": cat.asset_type, "method": cat.method, "method_number": cat.method_number,
                "method_period": cat.method_period, "degressive_factor": cat.degressive_factor,
                "prorata": cat.prorata, "auto_post": cat.auto_post}

    @api.model_create_multi
    def create(self, vals_list):
        cats = self.env["acc.asset.category"]
        for vals in vals_list:
            cat = cats.browse(vals.get("category_id"))
            if cat.exists():
                for k, v in self._vals_from_category(cat).items():
                    vals.setdefault(k, v)
        return super().create(vals_list)

    @api.constrains("value", "salvage_value", "method_number", "method_period")
    def _check_values(self):
        for asset in self:
            if asset.method_number <= 0 or asset.method_period <= 0:
                raise ValidationError(_("The number of periods and the period length must be positive."))
            if asset.salvage_value > asset.value:
                raise ValidationError(_("The salvage value cannot be higher than the gross value."))

    # ------------------------------------------------------------------ board
    @staticmethod
    def _month_end(day):
        return day.replace(day=calendar.monthrange(day.year, day.month)[1])

    def _first_period_end(self):
        if self.first_depreciation_date:
            return self.first_depreciation_date
        end = self.date + relativedelta(months=self.method_period - 1)
        return self._month_end(end)

    def _depreciation_plan(self):
        """Return a list of (date, amount) for the remaining (not posted) part of the board."""
        self.ensure_one()
        cur = self.currency_id
        posted = self.line_ids.filtered(lambda l: l.move_id)
        base = self.value - self.salvage_value - self.already_depreciated - sum(posted.mapped("amount"))
        if cur.is_zero(base) or base < 0:
            return []
        n_total = self.method_number
        done_n = len(posted)
        period_end = self._first_period_end() + relativedelta(months=self.method_period * done_n)
        period_end = self._month_end(period_end) if not self.first_depreciation_date else period_end
        first_factor = 1.0
        if self.prorata:
            fp_end = self._first_period_end()
            period_start = fp_end - relativedelta(months=self.method_period) + relativedelta(days=1)
            days = (fp_end - period_start).days + 1
            used = (fp_end - self.date).days + 1
            first_factor = max(0.0, min(1.0, used / float(days or 1)))
        total_n = n_total + (1 if first_factor < 0.9999 else 0)
        linear_amount = (self.value - self.salvage_value - self.already_depreciated) / float(n_total)
        plan, residual, i = [], base, 0
        while not cur.is_zero(residual) and residual > 0 and i < 1200:
            left = total_n - done_n - i
            if self.method == "degressive":
                amount = max(residual * self.degressive_factor / float(n_total), residual / float(max(left, 1)))
            else:
                amount = linear_amount
            if i == 0 and not done_n:
                amount *= first_factor
            amount = cur.round(residual) if left <= 1 else cur.round(min(amount, residual))
            plan.append((period_end, amount))
            residual = cur.round(residual - amount)
            i += 1
            nxt = period_end + relativedelta(months=self.method_period)
            period_end = nxt if self.first_depreciation_date else self._month_end(nxt)
        return plan

    def compute_depreciation_board(self):
        for asset in self:
            if asset.state in ("close", "cancel"):
                continue
            asset.line_ids.filtered(lambda l: not l.move_id).unlink()
            posted = asset.line_ids
            seq = len(posted)
            cumul = asset.already_depreciated + sum(posted.mapped("amount"))
            vals = []
            for day, amount in asset._depreciation_plan():
                seq += 1
                cumul += amount
                vals.append({"asset_id": asset.id, "sequence": seq, "date": day, "amount": amount,
                             "depreciated_value": cumul, "remaining_value": asset.value - asset.salvage_value - cumul})
            self.env["acc.asset.line"].create(vals)
        return True

    # ------------------------------------------------------------------ workflow
    def action_confirm(self):
        for asset in self:
            if asset.state != "draft":
                continue
            if not asset.line_ids:
                asset.compute_depreciation_board()
            asset.state = "open"
        return True

    def action_set_draft(self):
        for asset in self:
            if asset.line_ids.filtered(lambda l: l.move_id and l.move_id.state == "posted"):
                raise UserError(_("Asset %s already has posted entries. Reverse them before resetting to draft.") % asset.name)
            asset.line_ids.mapped("move_id").filtered(lambda m: m.state == "draft").unlink()
            asset.state = "draft"
        return True

    def action_cancel(self):
        for asset in self:
            if asset.line_ids.filtered(lambda l: l.move_id and l.move_id.state == "posted"):
                raise UserError(_("Asset %s already has posted entries; dispose of it instead.") % asset.name)
            asset.line_ids.mapped("move_id").filtered(lambda m: m.state == "draft").unlink()
            asset.state = "cancel"
        return True

    def action_post_due(self, day=None):
        """Create (and post) the depreciation entries due up to ``day`` (default today)."""
        day = day or fields.Date.context_today(self)
        lines = self.mapped("line_ids").filtered(lambda l: not l.move_id and l.date <= day and l.asset_id.state == "open")
        lines.create_move()
        for asset in self.filtered(lambda a: a.state == "open"):
            if asset.line_ids and all(l.move_id and l.move_id.state == "posted" for l in asset.line_ids):
                asset.state = "close"
        return True

    @api.model
    def _cron_post_depreciation(self):
        assets = self.search([("state", "=", "open")])
        assets.action_post_due()

    def action_view_entries(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Entries"), "res_model": "account.move",
                "views": self.env["acc.report.engine"]._views_for("account.move"), "domain": [("id", "in", self.move_ids.ids)],
                "context": {"create": False}}

    def action_open_dispose(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Dispose / Sell Asset"), "res_model": "acc.asset.dispose",
                "view_mode": "form", "views": [(False, "form")], "target": "new", "context": {"default_asset_id": self.id}}

    @api.model
    def _action_for_type(self, asset_type):
        xmlid = {"asset": "accounting_asset_heapdev.action_acc_asset",
                 "expense": "accounting_asset_heapdev.action_acc_deferred_expense",
                 "revenue": "accounting_asset_heapdev.action_acc_deferred_revenue"}[asset_type or "asset"]
        return self.env["ir.actions.act_window"]._for_xml_id(xmlid)

    def unlink(self):
        if self.filtered(lambda a: a.state in ("open", "close")):
            raise UserError(_("Only draft or cancelled assets can be deleted."))
        return super().unlink()


class AccAssetLine(models.Model):
    _name = "acc.asset.line"
    _description = "Depreciation Line"
    _order = "asset_id, sequence, date"

    asset_id = fields.Many2one("acc.asset", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer()
    date = fields.Date(required=True)
    amount = fields.Monetary(string="Amount", required=True)
    depreciated_value = fields.Monetary(string="Cumulative")
    remaining_value = fields.Monetary(string="Remaining")
    currency_id = fields.Many2one(related="asset_id.currency_id")
    company_id = fields.Many2one(related="asset_id.company_id", store=True)
    move_id = fields.Many2one("account.move", string="Entry", copy=False, ondelete="set null")
    move_state = fields.Selection(related="move_id.state", string="Entry Status")
    move_check = fields.Boolean(string="Linked", compute="_compute_move_check", store=True)

    @api.depends("move_id")
    def _compute_move_check(self):
        for line in self:
            line.move_check = bool(line.move_id)

    def _move_vals(self):
        self.ensure_one()
        asset = self.asset_id
        cat = asset.category_id
        amount = self.amount
        if asset.asset_type == "revenue":
            debit_acc, credit_acc = cat.account_depreciation_id, cat.account_expense_id
        else:
            debit_acc, credit_acc = cat.account_expense_id, cat.account_depreciation_id
        label = "%s (%s/%s)" % (asset.name, self.sequence, len(asset.line_ids))
        common = {"name": label, "partner_id": asset.partner_id.id or False}
        return {
            "move_type": "entry",
            "journal_id": cat.journal_id.id,
            "date": self.date,
            "ref": label,
            "acc_asset_id": asset.id,
            "line_ids": [
                (0, 0, dict(common, account_id=debit_acc.id, debit=amount, credit=0.0)),
                (0, 0, dict(common, account_id=credit_acc.id, debit=0.0, credit=amount)),
            ],
        }

    def create_move(self):
        moves = self.env["account.move"]
        for line in self:
            if line.move_id or line.asset_id.currency_id.is_zero(line.amount):
                continue
            move = self.env["account.move"].create(line._move_vals())
            line.move_id = move
            moves |= move
        to_post = moves.filtered(lambda m: m.acc_asset_id.auto_post)
        if to_post:
            to_post._post()
        return moves

    def action_create_move(self):
        self.create_move()
        self.mapped("asset_id").filtered(
            lambda a: a.line_ids and all(l.move_id and l.move_id.state == "posted" for l in a.line_ids)).write({"state": "close"})
        return True

    def unlink(self):
        if self.filtered(lambda l: l.move_id and l.move_id.state == "posted"):
            raise UserError(_("You cannot delete a depreciation line with a posted entry."))
        return super().unlink()

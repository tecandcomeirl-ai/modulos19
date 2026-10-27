# -*- coding: utf-8 -*-
import base64
from collections import defaultdict

from markupsafe import Markup, escape

from odoo import _, api, fields, models, release
from odoo.exceptions import UserError

V = release.version_info[0]
BUCKETS = [(0, 0, "Not due"), (1, 30, "1-30"), (31, 60, "31-60"), (61, 90, "61-90"), (91, 100000, "90+")]

def _acc_flush(env):
    """Write pending ORM changes to the database before raw SQL (Odoo 16+ no longer flushes on cr.execute)."""
    if hasattr(env, "flush_all"):
        env.flush_all()
    else:
        env["base"].flush()

class AccFollowupLevel(models.Model):
    _name = "acc.followup.level"
    _description = "Follow-up Level"
    _order = "delay, sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    delay = fields.Integer(string="Days Overdue", required=True, help="Applies when the oldest overdue invoice is late by at least this number of days.")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    send_email = fields.Boolean(string="Send Email", default=True)
    print_letter = fields.Boolean(string="Print Letter")
    manual_action = fields.Boolean(string="Manual Action")
    manual_action_note = fields.Text(string="Action To Do")
    description = fields.Text(string="Message", translate=True,
                              help="Placeholders: {partner}, {company}, {total_due}, {total_overdue}, {date}")
    active = fields.Boolean(default=True)

    def render_message(self, partner):
        self.ensure_one()
        cur = partner.env.company.currency_id
        vals = {"partner": partner.name, "company": partner.env.company.name, "date": fields.Date.context_today(self),
                "total_due": "%s %s" % (cur.symbol, "{:,.2f}".format(partner.acc_total_due)),
                "total_overdue": "%s %s" % (cur.symbol, "{:,.2f}".format(partner.acc_total_overdue))}
        text = self.description or ""
        for k, v in vals.items():
            text = text.replace("{%s}" % k, str(v))
        return text


class ResPartner(models.Model):
    _inherit = "res.partner"

    acc_total_due = fields.Monetary(string="Total Due", compute="_compute_acc_followup", currency_field="acc_currency_id")
    acc_total_overdue = fields.Monetary(string="Total Overdue", compute="_compute_acc_followup", currency_field="acc_currency_id")
    acc_overdue_days = fields.Integer(string="Days Overdue", compute="_compute_acc_followup")
    acc_followup_level_id = fields.Many2one("acc.followup.level", string="Follow-up Level", compute="_compute_acc_followup")
    acc_has_overdue = fields.Boolean(compute="_compute_acc_followup", search="_search_acc_has_overdue", string="Has Overdue")
    acc_has_due = fields.Boolean(compute="_compute_acc_followup", search="_search_acc_has_due", string="Has Due")
    acc_currency_id = fields.Many2one("res.currency", compute="_compute_acc_currency")
    acc_followup_last_date = fields.Date(string="Last Follow-up", copy=False)
    acc_followup_next_date = fields.Date(string="Next Action Date", copy=False)
    acc_followup_note = fields.Text(string="Follow-up Notes", copy=False)
    acc_followup_responsible_id = fields.Many2one("res.users", string="Follow-up Responsible", copy=False)
    acc_open_aml_ids = fields.Many2many("account.move.line", compute="_compute_acc_open_amls", string="Open Items")

    def _compute_acc_currency(self):
        for p in self:
            p.acc_currency_id = self.env.company.currency_id

    @api.model
    def _acc_receivable_sql(self):
        return "a.internal_type = 'receivable'" if V <= 15 else "a.account_type = 'asset_receivable'"

    @api.model
    def _acc_followup_data(self, partner_ids=None):
        today = fields.Date.context_today(self)
        q = """
            SELECT p.commercial_partner_id,
                   SUM(aml.amount_residual),
                   SUM(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s THEN aml.amount_residual ELSE 0 END),
                   MIN(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s AND aml.amount_residual > 0 THEN COALESCE(aml.date_maturity, aml.date) END)
              FROM account_move_line aml
              JOIN account_account a ON a.id = aml.account_id
              JOIN res_partner p ON p.id = aml.partner_id
             WHERE aml.parent_state = 'posted' AND aml.reconciled IS NOT TRUE AND aml.company_id = %s AND {acc}
               {partners}
          GROUP BY p.commercial_partner_id
        """.format(acc=self._acc_receivable_sql(), partners="AND p.commercial_partner_id = ANY(%s)" if partner_ids is not None else "")
        params = [today, today, self.env.company.id] + ([list(partner_ids)] if partner_ids is not None else [])
        _acc_flush(self.env)
        self.env.cr.execute(q, params)
        return {r[0]: (r[1] or 0.0, r[2] or 0.0, (today - r[3]).days if r[3] else 0) for r in self.env.cr.fetchall()}

    def _compute_acc_followup(self):
        data = self._acc_followup_data([p.commercial_partner_id.id for p in self if p.commercial_partner_id]) if self.ids else {}
        levels = self.env["acc.followup.level"].search([("company_id", "=", self.env.company.id)], order="delay")
        for p in self:
            due, overdue, days = data.get(p.commercial_partner_id.id, (0.0, 0.0, 0))
            p.acc_total_due = due
            p.acc_total_overdue = overdue
            p.acc_overdue_days = days
            p.acc_has_overdue = overdue > 0.005
            p.acc_has_due = due > 0.005
            lvl = levels.filtered(lambda l: l.delay <= days) if overdue > 0.005 else levels.browse()
            p.acc_followup_level_id = lvl[-1:] if lvl else False

    @api.model
    def _acc_positive(self, operator, value):
        if operator in ("in", "not in"):  # Odoo 17+ normalises '=' True into 'in' [True]
            return any(value) == (operator == "in")
        return bool(value) == (operator in ("=", "=="))

    def _search_acc_has_overdue(self, operator, value):
        ids = [pid for pid, v in self._acc_followup_data().items() if v[1] > 0.005]
        positive = self._acc_positive(operator, value)
        return [("id", "in" if positive else "not in", ids)]

    def _search_acc_has_due(self, operator, value):
        ids = [pid for pid, v in self._acc_followup_data().items() if v[0] > 0.005]
        positive = self._acc_positive(operator, value)
        return [("id", "in" if positive else "not in", ids)]

    def _acc_open_amls(self):
        self.ensure_one()
        dom = [("partner_id", "child_of", self.commercial_partner_id.id), ("parent_state", "=", "posted"), ("reconciled", "=", False),
               ("company_id", "=", self.env.company.id)]
        dom.append(("account_id.internal_type", "=", "receivable") if V <= 15 else ("account_id.account_type", "=", "asset_receivable"))
        return self.env["account.move.line"].search(dom, order="date_maturity, date, id")

    def _compute_acc_open_amls(self):
        for p in self:
            p.acc_open_aml_ids = p._acc_open_amls() if p.id else self.env["account.move.line"]

    def _acc_statement_values(self):
        """Values for the customer statement / reminder (shared by PDF and email)."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        rows, buckets = [], defaultdict(float)
        for l in self._acc_open_amls():
            due = l.date_maturity or l.date
            days = (today - due).days
            label = next(b[2] for b in BUCKETS if b[0] <= max(days, 0) <= b[1])
            buckets[label] += l.amount_residual
            rows.append({"date": l.date, "move": l.move_id.name, "ref": l.move_id.ref or l.name or "", "due": due,
                         "amount": l.balance, "residual": l.amount_residual, "days": max(days, 0), "overdue": days > 0})
        return {"rows": rows, "buckets": [(b[2], buckets.get(b[2], 0.0)) for b in BUCKETS], "today": today,
                "total": sum(r["residual"] for r in rows), "overdue": sum(r["residual"] for r in rows if r["overdue"]),
                "level": self.acc_followup_level_id, "message": self.acc_followup_level_id.render_message(self) if self.acc_followup_level_id else ""}

    def _acc_email_body(self):
        vals = self._acc_statement_values()
        cur = self.env.company.currency_id
        fmt = lambda v: "{:,.2f}".format(v)
        msg = escape(vals["message"] or _("Dear %s,\n\nPlease find below the statement of your open invoices.") % self.name).replace("\n", Markup("<br/>"))
        rows = Markup("").join(Markup(
            "<tr><td style='padding:4px 8px;border-bottom:1px solid #eee'>%s</td><td style='padding:4px 8px;border-bottom:1px solid #eee'>%s</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee'>%s</td><td style='padding:4px 8px;border-bottom:1px solid #eee;text-align:right'>%s</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;text-align:right;color:%s'>%s</td></tr>")
            % (r["move"], r["ref"], r["due"], fmt(r["amount"]), "#c43d3d" if r["overdue"] else "#333", fmt(r["residual"])) for r in vals["rows"])
        head = Markup("<tr style='background:#f3f6fa'><th style='padding:6px 8px;text-align:left'>%s</th><th style='padding:6px 8px;text-align:left'>%s</th>"
                      "<th style='padding:6px 8px;text-align:left'>%s</th><th style='padding:6px 8px;text-align:right'>%s</th><th style='padding:6px 8px;text-align:right'>%s</th></tr>") % (
            _("Invoice"), _("Reference"), _("Due Date"), _("Amount"), _("Open"))
        total = Markup("<p style='margin-top:10px'><b>%s: %s %s</b> &#183; %s: %s %s</p>") % (
            _("Total due"), cur.symbol, fmt(vals["total"]), _("Overdue"), cur.symbol, fmt(vals["overdue"]))
        return Markup("<div style='font-family:Arial,sans-serif;font-size:13px'><p>%s</p><table style='border-collapse:collapse;width:100%%'>%s%s</table>%s</div>") % (msg, head, rows, total)

    def _acc_statement_pdf(self):
        report = self.env.ref("accounting_followup_heapdev.action_report_acc_customer_statement")
        try:
            if V >= 16:
                pdf = self.env["ir.actions.report"]._render_qweb_pdf(report.report_name, self.ids)[0]
            else:
                pdf = report._render_qweb_pdf(self.ids)[0]
        except Exception:  # wkhtmltopdf missing or broken: send the email without PDF
            return False
        att_vals = {"name": _("Statement - %s.pdf") % self.name, "res_model": "res.partner", "res_id": self.id, "mimetype": "application/pdf"}
        att_vals["raw"] = pdf
        return self.env["ir.attachment"].create(att_vals)

    def action_acc_followup_email(self):
        self.ensure_one()
        partner = self.commercial_partner_id
        if not partner.email:
            raise UserError(_("Set an email address on %s first.") % partner.name)
        att = partner._acc_statement_pdf()
        ctx = {"default_model": "res.partner", "default_composition_mode": "comment",
               "default_subject": _("%s - Payment reminder") % self.env.company.name, "default_body": partner._acc_email_body(),
               "default_partner_ids": [partner.id], "default_attachment_ids": [att.id] if att else []}
        if V >= 17:
            ctx["default_res_ids"] = [partner.id]
        else:
            ctx["default_res_id"] = partner.id
        partner._acc_mark_followed()
        return {"type": "ir.actions.act_window", "res_model": "mail.compose.message", "view_mode": "form", "views": [(False, "form")], "target": "new",
                "name": _("Payment Reminder"), "context": ctx}

    def action_acc_print_statement(self):
        self._acc_mark_followed()
        return self.env.ref("accounting_followup_heapdev.action_report_acc_customer_statement").report_action(self.mapped("commercial_partner_id"))

    def _acc_mark_followed(self):
        today = fields.Date.context_today(self)
        for p in self:
            nxt = self.env["acc.followup.level"].search([("company_id", "=", self.env.company.id), ("delay", ">", p.acc_overdue_days)], order="delay", limit=1)
            p.write({"acc_followup_last_date": today,
                     "acc_followup_next_date": fields.Date.add(today, days=(nxt.delay - p.acc_overdue_days) if nxt else 14)})

    def action_acc_done(self):
        self._acc_mark_followed()
        return True

    def action_acc_open_items(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Open Items"), "res_model": "account.move.line",
                "views": [(self.env.ref("account.view_move_line_tree").id, "tree" if V in (16, 17) else "list"), (self.env.ref("account.view_move_line_form").id, "form")], "domain": [("id", "in", self._acc_open_amls().ids)],
                "context": {"create": False}}

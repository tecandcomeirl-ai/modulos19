# -*- coding: utf-8 -*-
import json
from datetime import date

from dateutil.relativedelta import relativedelta
from markupsafe import escape

from odoo import _, models, release

V = release.version_info[0]
OI = {"fa-line-chart": "show_chart", "fa-credit-card": "credit_card", "fa-calculator": "calculate", "fa-university": "account_balance",
      "fa-users": "group", "fa-building": "business", "fa-file-text-o": "description", "fa-exclamation-triangle": "warning"}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
INCOME = ("income", "income_other")
EXPENSE = ("expense", "expense_depreciation", "expense_direct_cost")

def _acc_flush(env):
    """Write pending ORM changes to the database before raw SQL (Odoo 16+ no longer flushes on cr.execute)."""
    if hasattr(env, "flush_all"):
        env.flush_all()
    else:
        env["base"].flush()

class AccReportEngineDashboard(models.AbstractModel):
    _inherit = "acc.report.engine"

    def _report_meta(self):
        res = super()._report_meta()
        res["dashboard"] = {"title": _("Accounting Dashboard"), "title_ar": "لوحة المعلومات المحاسبية", "filters": ["date", "posted"]}
        return res

    def _dash_sum(self, options, types, date_from=None, date_to=None, sign=1):
        accs = self._accounts_of(types)
        bal = self._balances(options, date_from=date_from, date_to=date_to, accounts=accs, partners=False, journals=False, analytic=False)
        return sign * sum(v[2] for v in bal.values())

    def _kpi(self, label, value, hint="", color="blue", icon="fa-line-chart", drill=None):
        attrs = ' data-acc="drill" data-params="%s"' % escape(json.dumps(drill)) if drill else ""
        ico = '<i class="oi" data-icon="%s"></i>' % OI.get(icon, "circle") if V >= 20 else '<i class="fa %s"></i>' % icon
        return ('<div class="o_acc_kpi o_acc_kpi_%s"%s><div class="o_acc_kpi_icon">%s</div>'
                '<div class="o_acc_kpi_label">%s</div><div class="o_acc_kpi_value">%s</div><div class="o_acc_kpi_hint">%s</div></div>'
                % (color, attrs, ico, escape(label), escape(value), hint))

    def _report_dashboard(self, options):
        df, dt = self._to_date(options["date_from"]), self._to_date(options["date_to"])
        cur = self._currency()
        sym = cur.symbol or ""
        money = lambda v: "%s %s" % (sym, self._fmt(v))
        income = self._dash_sum(options, INCOME, df, dt, -1)
        expense = self._dash_sum(options, EXPENSE, df, dt, 1)
        net = income - expense
        span = (dt - df).days + 1
        pdf_, pdt = df - relativedelta(days=span), df - relativedelta(days=1)
        prev_income = self._dash_sum(options, INCOME, pdf_, pdt, -1)
        cash = self._dash_sum(options, ("asset_cash",), None, dt, 1)
        receivable = self._dash_sum(options, ("asset_receivable",), None, dt, 1)
        payable = self._dash_sum(options, ("liability_payable",), None, dt, -1)
        # overdue receivables (open items due before date_to)
        rec_accs = self._accounts_of(("asset_receivable",))
        _acc_flush(self.env)
        self.env.cr.execute("""SELECT COALESCE(SUM(aml.amount_residual), 0) FROM account_move_line aml
                                WHERE aml.company_id = %s AND aml.parent_state = 'posted' AND aml.reconciled IS NOT TRUE
                                  AND aml.account_id = ANY(%s) AND COALESCE(aml.date_maturity, aml.date) < %s""",
                            [self._company().id, rec_accs or [0], dt])
        overdue = self.env.cr.fetchone()[0] or 0.0
        # VAT for the period from tax lines
        _acc_flush(self.env)
        self.env.cr.execute("""SELECT COALESCE(SUM(CASE WHEN t.type_tax_use = 'sale' THEN -aml.balance ELSE 0 END), 0),
                                      COALESCE(SUM(CASE WHEN t.type_tax_use = 'purchase' THEN aml.balance ELSE 0 END), 0)
                                 FROM account_move_line aml JOIN account_tax t ON t.id = aml.tax_line_id
                                WHERE aml.company_id = %s AND aml.parent_state = 'posted' AND aml.date >= %s AND aml.date <= %s""",
                            [self._company().id, df, dt])
        vat_out, vat_in = self.env.cr.fetchone()
        growth = ((income - prev_income) / abs(prev_income) * 100.0) if abs(prev_income) > 0.005 else 0.0
        trend = '<span class="%s">%s%.1f%%</span> %s' % ("o_acc_up" if growth >= 0 else "o_acc_down", "+" if growth >= 0 else "", growth, escape(_("vs previous period")))
        margin = (net / income * 100.0) if income else 0.0
        cards = [
            self._kpi(_("Revenue"), money(income), trend, "blue", "fa-line-chart", {"type": "report", "report": "pl"}),
            self._kpi(_("Expenses"), money(expense), escape(_("Cost of revenue and operating expenses")), "amber", "fa-credit-card", {"type": "report", "report": "pl"}),
            self._kpi(_("Net Profit"), money(net), escape(_("Net margin %.1f%%") % margin), "green" if net >= 0 else "red", "fa-calculator", {"type": "report", "report": "pl"}),
            self._kpi(_("Cash & Bank"), money(cash), escape(_("Balance on %s") % self._fmt_date(dt)), "teal", "fa-university", {"type": "report", "report": "cf"}),
            self._kpi(_("Receivables"), money(receivable), escape(_("Overdue %s") % money(overdue)), "purple", "fa-users", {"type": "report", "report": "aged_receivable"}),
            self._kpi(_("Payables"), money(payable), escape(_("Open vendor balance")), "red", "fa-building", {"type": "report", "report": "aged_payable"}),
            self._kpi(_("VAT Payable"), money(vat_out - vat_in), escape(_("Output %s · Input %s") % (self._fmt(vat_out), self._fmt(vat_in))), "blue", "fa-file-text-o", {"type": "report", "report": "tax"}),
            self._kpi(_("Overdue Receivables"), money(overdue), escape(_("%.0f%% of receivables") % ((overdue / receivable * 100.0) if receivable else 0.0)), "amber", "fa-exclamation-triangle", {"type": "report", "report": "aged_receivable"}),
        ]
        # monthly series: last 12 months ending with date_to
        first = date(dt.year, dt.month, 1) - relativedelta(months=11)
        inc_accs, exp_accs, cash_accs = self._accounts_of(INCOME), self._accounts_of(EXPENSE), self._accounts_of(("asset_cash",))
        where, params = self._where(options, date_from=first, date_to=dt, partners=False, journals=False, analytic=False)
        _acc_flush(self.env)
        self.env.cr.execute("""SELECT date_trunc('month', aml.date)::date,
                                      SUM(CASE WHEN aml.account_id = ANY(%%s) THEN -aml.balance ELSE 0 END),
                                      SUM(CASE WHEN aml.account_id = ANY(%%s) THEN aml.balance ELSE 0 END),
                                      SUM(CASE WHEN aml.account_id = ANY(%%s) THEN aml.balance ELSE 0 END)
                                 FROM account_move_line aml WHERE %s GROUP BY 1""" % where,
                            [inc_accs or [0], exp_accs or [0], cash_accs or [0]] + params)
        by_month = {r[0]: r[1:] for r in self.env.cr.fetchall()}
        labels, inc_s, exp_s, cash_s = [], [], [], []
        running = self._dash_sum(options, ("asset_cash",), None, first - relativedelta(days=1), 1)
        for i in range(12):
            m = first + relativedelta(months=i)
            vals = by_month.get(m, (0.0, 0.0, 0.0))
            labels.append("%s %s" % (MONTHS[m.month - 1], str(m.year)[2:]))
            inc_s.append(vals[0] or 0.0)
            exp_s.append(vals[1] or 0.0)
            running += vals[2] or 0.0
            cash_s.append(running)
        bars = self._svg_bars(labels, [(_("Income"), inc_s), (_("Expenses"), exp_s)], ["#1d5fa8", "#f0a020"], height=240, width=720)
        line = self._svg_line(labels, cash_s, "#0f9d8a", height=240, width=720)
        # aged receivable donut
        _acc_flush(self.env)
        self.env.cr.execute("""SELECT COALESCE(aml.date_maturity, aml.date), aml.amount_residual FROM account_move_line aml
                                WHERE aml.company_id = %s AND aml.parent_state = 'posted' AND aml.reconciled IS NOT TRUE AND aml.account_id = ANY(%s)""",
                            [self._company().id, rec_accs or [0]])
        buckets = [[_("Not due"), 0.0], ["1-30", 0.0], ["31-60", 0.0], ["61-90", 0.0], ["90+", 0.0]]
        for due, res in self.env.cr.fetchall():
            days = (dt - due).days
            idx = 0 if days <= 0 else 1 if days <= 30 else 2 if days <= 60 else 3 if days <= 90 else 4
            buckets[idx][1] += res or 0.0
        dcolors = ["#10a37f", "#2b6cd4", "#f0a020", "#e2763a", "#d13c3c"]
        donut = self._svg_donut([(b[0], b[1]) for b in buckets], dcolors)
        dtable = "".join('<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:%s"></i> %s</td><td style="text-align:right">%s</td></tr>'
                         % (c, escape(b[0]), self._fmt(b[1])) for b, c in zip(buckets, dcolors))
        # top customers and top expenses
        _acc_flush(self.env)
        self.env.cr.execute("""SELECT p.name, -SUM(aml.balance) FROM account_move_line aml JOIN res_partner p ON p.id = aml.partner_id
                                WHERE %s AND aml.account_id = ANY(%%s) GROUP BY p.name ORDER BY 2 DESC LIMIT 6""" % self._where(options, date_from=df, date_to=dt, partners=False, journals=False, analytic=False)[0],
                            self._where(options, date_from=df, date_to=dt, partners=False, journals=False, analytic=False)[1] + [inc_accs or [0]])
        top_c = [(r[0] if isinstance(r[0], str) else (r[0] or {}).get("en_US", ""), r[1] or 0.0) for r in self.env.cr.fetchall()]
        exp_bal = self._balances(options, date_from=df, date_to=dt, accounts=exp_accs, partners=False, journals=False, analytic=False)
        accounts = self._accounts()
        top_e = sorted([(accounts[a]["name"], v[2]) for a, v in exp_bal.items() if a in accounts], key=lambda x: -x[1])[:6]
        legend = lambda items: '<div class="o_acc_legend">%s</div>' % "".join('<span><i style="background:%s"></i>%s</span>' % (c, escape(n)) for n, c in items)
        card = lambda title, sub, body: '<div class="o_acc_card"><h4>%s <small>%s</small></h4>%s</div>' % (escape(title), escape(sub), body)
        blocks = [
            '<div class="o_acc_kpis">%s</div>' % "".join(cards),
            '<div class="o_acc_cards">%s%s</div>' % (
                card(_("Income vs Expenses"), _("Last 12 months"), bars + legend([(_("Income"), "#1d5fa8"), (_("Expenses"), "#f0a020")])),
                card(_("Cash & Bank Balance"), _("Month end"), line)),
            '<div class="o_acc_cards">%s%s%s</div>' % (
                card(_("Receivables Aging"), self._fmt_date(dt), '<div class="o_acc_donut_wrap">%s<table>%s</table></div>' % (donut, dtable)),
                card(_("Top Customers"), _("Revenue in period"), self._svg_hbars(top_c, "#1d5fa8")),
                card(_("Top Expenses"), _("In period"), self._svg_hbars(top_e, "#f0a020"))),
        ]
        return {"columns": [], "lines": [], "blocks": blocks}

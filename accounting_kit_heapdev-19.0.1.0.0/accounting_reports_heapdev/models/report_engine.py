# -*- coding: utf-8 -*-
import io
import json
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models, release
from odoo.exceptions import AccessError, UserError

from .ar_labels import ar

V = release.version_info[0]

# normalised account types (Odoo 16+ naming); 14/15 user types are mapped onto them
TYPE_XMLID_14 = {
    "account.data_account_type_receivable": "asset_receivable",
    "account.data_account_type_payable": "liability_payable",
    "account.data_account_type_liquidity": "asset_cash",
    "account.data_account_type_current_assets": "asset_current",
    "account.data_account_type_non_current_assets": "asset_non_current",
    "account.data_account_type_prepayments": "asset_prepayments",
    "account.data_account_type_fixed_assets": "asset_fixed",
    "account.data_account_type_current_liabilities": "liability_current",
    "account.data_account_type_non_current_liabilities": "liability_non_current",
    "account.data_account_type_credit_card": "liability_credit_card",
    "account.data_account_type_equity": "equity",
    "account.data_unaffected_earnings": "equity_unaffected",
    "account.data_account_type_revenue": "income",
    "account.data_account_type_other_income": "income_other",
    "account.data_account_type_expenses": "expense",
    "account.data_account_type_depreciation": "expense_depreciation",
    "account.data_account_type_direct_costs": "expense_direct_cost",
    "account.data_account_off_sheet": "off_balance",
}
GROUP_FALLBACK = {"asset": "asset_current", "liability": "liability_current", "equity": "equity",
                  "income": "income", "expense": "expense", "off_balance": "off_balance"}
_ACC_CACHE = {}
PRESET_KEYS = ("month", "quarter", "year", "last_month", "last_quarter", "last_year")
PL_TYPES = ("income", "income_other", "expense", "expense_depreciation", "expense_direct_cost")

def _acc_flush(env):
    """Write pending ORM changes to the database before raw SQL (Odoo 16+ no longer flushes on cr.execute)."""
    if hasattr(env, "flush_all"):
        env.flush_all()
    else:
        env["base"].flush()

class AccReportEngine(models.AbstractModel):
    _name = "acc.report.engine"
    _description = "Accounting Reports Engine"

    # ------------------------------------------------------------------ meta
    def _report_meta(self):
        """key -> metadata. Other modules extend this (dashboard, budget)."""
        return {
            "pl": {"title": _("Profit and Loss"), "title_ar": ar("Profit and Loss"), "filters": ["date", "comparison", "journals", "analytic", "posted"]},
            "bs": {"title": _("Balance Sheet"), "title_ar": ar("Balance Sheet"), "filters": ["asof", "comparison", "journals", "analytic", "posted"]},
            "cf": {"title": _("Cash Flow Statement"), "title_ar": ar("Cash Flow Statement"), "filters": ["date", "journals", "posted"]},
            "gl": {"title": _("General Ledger"), "title_ar": ar("General Ledger"), "filters": ["date", "journals", "analytic", "partners", "posted", "fold"]},
            "tb": {"title": _("Trial Balance"), "title_ar": ar("Trial Balance"), "filters": ["date", "journals", "analytic", "posted"]},
            "partner_ledger": {"title": _("Partner Ledger"), "title_ar": ar("Partner Ledger"), "filters": ["date", "journals", "partners", "account_kind", "posted", "fold"]},
            "journal_audit": {"title": _("Journal Audit"), "title_ar": ar("Journal Audit"), "filters": ["date", "journals", "posted", "fold"]},
            "aged_receivable": {"title": _("Aged Receivable"), "title_ar": ar("Aged Receivable"), "filters": ["asof", "partners", "posted", "fold"]},
            "aged_payable": {"title": _("Aged Payable"), "title_ar": ar("Aged Payable"), "filters": ["asof", "partners", "posted", "fold"]},
            "tax": {"title": _("Tax Report"), "title_ar": ar("Tax Report"), "filters": ["date", "journals", "posted"]},
        }

    def _check_access(self):
        user = self.env.user
        if not (user.has_group("account.group_account_readonly") or user.has_group("account.group_account_invoice")):
            raise AccessError(_("You need accounting access rights to open financial reports."))

    # ------------------------------------------------------------------ options
    def _to_date(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return fields.Date.from_string(str(value)[:10])

    def _fy(self, day):
        res = self.env.company.compute_fiscalyear_dates(day)
        return self._to_date(res["date_from"]), self._to_date(res["date_to"])

    def _preset_dates(self, preset, today):
        if preset == "today":
            return today, today
        if preset == "month":
            start = today.replace(day=1)
            return start, start + relativedelta(months=1, days=-1)
        if preset == "last_month":
            start = today.replace(day=1) - relativedelta(months=1)
            return start, start + relativedelta(months=1, days=-1)
        if preset in ("quarter", "last_quarter"):
            q = (today.month - 1) // 3
            start = date(today.year, q * 3 + 1, 1)
            if preset == "last_quarter":
                start -= relativedelta(months=3)
            return start, start + relativedelta(months=3, days=-1)
        if preset == "year":
            return self._fy(today)
        if preset == "last_year":
            return self._fy(self._fy(today)[0] - timedelta(days=1))
        return None, None

    def _normalize(self, options):
        options = dict(options or {})
        key = options.get("report") or "pl"
        meta = self._report_meta()
        if key not in meta:
            raise UserError(_("Unknown report: %s") % key)
        today = fields.Date.context_today(self)
        df, dt = self._to_date(options.get("date_from")), self._to_date(options.get("date_to"))
        preset = options.pop("preset", None)
        if preset:
            df, dt = self._preset_dates(preset, today)
            options["period"] = preset
        if not dt:
            dt = today
        if not df:
            df = self._fy(dt)[0]
        if df > dt:
            df, dt = dt, df

        def ids(name):
            return [int(x) for x in (options.get(name) or []) if str(x).isdigit()]

        def flag(name, default):
            val = options.get(name, default)
            return val not in (False, None, "false", "0", 0, "")

        comparison = max(0, min(3, int(options.get("comparison") or 0)))
        norm = {
            "report": key,
            "date_from": fields.Date.to_string(df),
            "date_to": fields.Date.to_string(dt),
            "period": options.get("period") or "custom",
            "posted_only": flag("posted_only", True),
            "journal_ids": ids("journal_ids"),
            "analytic_ids": ids("analytic_ids"),
            "partner_ids": ids("partner_ids"),
            "comparison": comparison,
            "comparison_mode": options.get("comparison_mode") if options.get("comparison_mode") in ("period", "year") else "period",
            "account_kind": options.get("account_kind") if options.get("account_kind") in ("receivable", "payable", "both") else "both",
            "unfold_all": flag("unfold_all", False),
            "hide_zero": flag("hide_zero", True),
        }
        for k, v in options.items():  # keep extension keys (x_budget_ids, ...)
            if k not in norm and k.startswith("x_"):
                norm[k] = v
        return norm

    # ------------------------------------------------------------------ helpers
    def _company(self):
        return self.env.company

    def _currency(self):
        return self._company().currency_id

    def _fmt(self, value, blank_zero=False):
        if value is None or value == "" or value is False:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, date):
            return self._fmt_date(value)
        digits = self._currency().decimal_places
        if abs(value) < 10 ** -digits / 2:
            if blank_zero:
                return ""
            value = 0.0
        return "{:,.{d}f}".format(value, d=digits)

    def _fmt_date(self, value):
        if not value:
            return ""
        value = self._to_date(value)
        lang = self.env["res.lang"].search([("code", "=", self.env.user.lang or "en_US")], limit=1)
        fmt = lang.date_format or "%m/%d/%Y"
        try:
            return value.strftime(fmt)
        except Exception:
            return fields.Date.to_string(value)

    def _period_label(self, df, dt):
        if df.day == 1 and dt == df + relativedelta(months=1, days=-1):
            return df.strftime("%b %Y")
        if df.day == 1 and df.month == 1 and dt.month == 12 and dt.day == 31 and df.year == dt.year:
            return str(df.year)
        if df.day == 1 and dt == df + relativedelta(months=3, days=-1):
            return "Q%d %d" % ((df.month - 1) // 3 + 1, df.year)
        return "%s - %s" % (self._fmt_date(df), self._fmt_date(dt))

    def _periods(self, options):
        df, dt = self._to_date(options["date_from"]), self._to_date(options["date_to"])
        cols = [(df, dt)]
        full_months = df.day == 1 and (dt + timedelta(days=1)).day == 1
        months = (dt.year - df.year) * 12 + dt.month - df.month + 1
        for i in range(1, options["comparison"] + 1):
            if options["comparison_mode"] == "year":
                cols.append((df - relativedelta(years=i), dt - relativedelta(years=i)))
            elif full_months:
                start = df - relativedelta(months=months * i)
                cols.append((start, start + relativedelta(months=months, days=-1)))
            else:
                length = (dt - df).days + 1
                cols.append((df - timedelta(days=length * i), dt - timedelta(days=length * i)))
        return cols

    def _accounts(self):
        key = (id(self.env.cr), self.env.company.id, self.env.lang)
        cached = _ACC_CACHE.get(key)
        if cached is not None:
            return cached
        Account = self.env["account.account"].with_context(active_test=False)
        accounts = Account.search([])
        info = {}
        if V <= 15:
            ext = accounts.mapped("user_type_id").get_external_id()
            for acc in accounts:
                t = TYPE_XMLID_14.get(ext.get(acc.user_type_id.id) or "") or GROUP_FALLBACK.get(acc.internal_group or "", "asset_current")
                if acc.internal_type == "receivable":
                    t = "asset_receivable"
                elif acc.internal_type == "payable":
                    t = "liability_payable"
                elif acc.internal_type == "liquidity":
                    t = "asset_cash"
                info[acc.id] = {"code": acc.code or "", "name": acc.name or "", "type": t}
        else:
            for acc in accounts:
                info[acc.id] = {"code": acc.code or "", "name": acc.name or "", "type": acc.account_type or "asset_current"}
        for v in info.values():
            v["display"] = ("%s %s" % (v["code"], v["name"])).strip()
        if len(_ACC_CACHE) > 50:
            _ACC_CACHE.clear()
        _ACC_CACHE[key] = info
        return info

    def _reset_cache(self):
        _ACC_CACHE.pop((id(self.env.cr), self.env.company.id, self.env.lang), None)

    def _accounts_of(self, types):
        return [aid for aid, v in self._accounts().items() if v["type"] in types]

    def _where(self, options, date_from=None, date_to=None, date_before=None, accounts=None, partners=True, journals=True, analytic=True):
        clauses = ["aml.company_id = %s", "aml.account_id IS NOT NULL"]
        params = [self._company().id]
        clauses.append("aml.parent_state = 'posted'" if options["posted_only"] else "aml.parent_state IN ('posted', 'draft')")
        if date_from:
            clauses.append("aml.date >= %s")
            params.append(date_from)
        if date_to:
            clauses.append("aml.date <= %s")
            params.append(date_to)
        if date_before:
            clauses.append("aml.date < %s")
            params.append(date_before)
        if accounts is not None:
            clauses.append("aml.account_id = ANY(%s)")
            params.append(list(accounts) or [0])
        if journals and options.get("journal_ids"):
            clauses.append("aml.journal_id = ANY(%s)")
            params.append(options["journal_ids"])
        if partners and options.get("partner_ids"):
            clauses.append("aml.partner_id = ANY(%s)")
            params.append(options["partner_ids"])
        if analytic and options.get("analytic_ids"):
            if V <= 15:
                clauses.append("aml.analytic_account_id = ANY(%s)")
                params.append(options["analytic_ids"])
            else:
                clauses.append("aml.analytic_distribution IS NOT NULL AND EXISTS (SELECT 1 FROM jsonb_object_keys(aml.analytic_distribution) k WHERE string_to_array(k, ',') && %s::text[])")
                params.append([str(i) for i in options["analytic_ids"]])
        return " AND ".join(clauses), params

    def _balances(self, options, **kw):
        where, params = self._where(options, **kw)
        _acc_flush(self.env)
        self.env.cr.execute("SELECT aml.account_id, SUM(aml.debit), SUM(aml.credit), SUM(aml.balance) FROM account_move_line aml WHERE %s GROUP BY aml.account_id" % where, params)
        return {r[0]: (r[1] or 0.0, r[2] or 0.0, r[3] or 0.0) for r in self.env.cr.fetchall()}

    def _aml_domain(self, options, date_from=None, date_to=None):
        dom = [("company_id", "=", self._company().id)]
        dom.append(("parent_state", "=", "posted") if options["posted_only"] else ("parent_state", "in", ["posted", "draft"]))
        if date_from:
            dom.append(("date", ">=", date_from))
        if date_to:
            dom.append(("date", "<=", date_to))
        if options.get("journal_ids"):
            dom.append(("journal_id", "in", options["journal_ids"]))
        if options.get("analytic_ids"):
            dom.append(("analytic_account_id" if V <= 15 else "analytic_distribution", "in", options["analytic_ids"]))
        return dom

    def _line(self, lid, name, values, level=0, style="line", parent=None, drill=None, name_ar="", foldable=False, cls=None):
        return {"id": lid, "name": name, "name_ar": name_ar, "values": values, "level": level, "style": style,
                "parent": parent, "drill": drill, "drill_json": json.dumps(drill) if drill else "", "foldable": foldable,
                "folded": False, "cls": list(cls or [])}

    def _col(self, label, label_ar="", kind="num"):
        return {"label": label, "label_ar": label_ar, "kind": kind}

    def _list_mode(self):
        # actions returned to the web client: 14/15 clients only know "list", 16/17 accept "tree", 18+ "list"
        return "tree" if V in (16, 17) else "list"

    def _views_for(self, model):
        """Pin the standard list/form views; on 14/15 the default (grouped) journal item list breaks outside its action."""
        refs = {"account.move.line": ("account.view_move_line_tree", "account.view_move_line_form"),
                "account.move": ("account.view_move_tree", "account.view_move_form")}.get(model)
        if refs:
            lst = self.env.ref(refs[0], raise_if_not_found=False)
            frm = self.env.ref(refs[1], raise_if_not_found=False)
            return [(lst.id if lst else False, self._list_mode()), (frm.id if frm else False, "form")]
        return [(False, self._list_mode()), (False, "form")]

    # ------------------------------------------------------------------ public API (called from the client action)
    @api.model
    def get_report_html(self, options):
        self._check_access()
        self._reset_cache()
        options = self._normalize(options)
        data = self._compute(options)
        values = self._render_values(options, data)
        html = self.env["ir.qweb"]._render("accounting_reports_heapdev.acc_report_screen", values)
        if isinstance(html, bytes):
            html = html.decode()
        return {"html": str(html), "options": options, "title": data["title"]}

    def _filter_partners(self):
        _acc_flush(self.env)
        self.env.cr.execute("SELECT DISTINCT partner_id FROM account_move_line WHERE partner_id IS NOT NULL AND company_id = %s LIMIT 500", [self._company().id])
        partners = self.env["res.partner"].browse([r[0] for r in self.env.cr.fetchall()]).exists()
        return partners.sorted(lambda p: (p.name or "").lower())

    def _render_values(self, options, data, pdf=False):
        meta = self._report_meta()[options["report"]]
        filters = meta.get("filters", [])
        journals = self.env["account.journal"].search([("company_id", "=", self._company().id)])
        analytics = self.env["account.analytic.account"].search([], limit=200) if "analytic" in filters else self.env["account.analytic.account"]
        partners = self._filter_partners() if "partners" in filters else self.env["res.partner"]
        sel = {
            "journals": journals.filtered(lambda j: j.id in options["journal_ids"]).mapped("name"),
            "analytics": analytics.filtered(lambda a: a.id in options["analytic_ids"]).mapped("name"),
            "partners": partners.filtered(lambda p: p.id in options["partner_ids"]).mapped("name"),
        }
        return {
            "data": data,
            "options": options,
            "meta": meta,
            "filters": filters,
            "journals": journals,
            "analytics": analytics,
            "partners": partners,
            "sel": sel,
            "fmt": self._fmt,
            "fmt_date": self._fmt_date,
            "company": self._company(),
            "currency": self._currency(),
            "pdf": pdf,
            "ar": ar,
            "presets": list(zip(PRESET_KEYS, [_("This Month"), _("This Quarter"), _("This Financial Year"),
                                              _("Last Month"), _("Last Quarter"), _("Last Financial Year")])),
            "printed_on": fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime("%Y-%m-%d %H:%M"),
            "is_num": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        }

    @api.model
    def action_drill(self, options, params):
        self._check_access()
        self._reset_cache()
        options = self._normalize(options)
        kind = params.get("type")
        if kind == "move":
            return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": int(params["move_id"]),
                    "views": [(False, "form")], "target": "current", "name": _("Journal Entry")}
        if kind == "record":
            return {"type": "ir.actions.act_window", "res_model": params["model"], "res_id": int(params["res_id"]),
                    "views": [(False, "form")], "target": "current", "name": params.get("name") or ""}
        if kind == "act_window":
            return {"type": "ir.actions.act_window", "res_model": params["model"], "name": params.get("name") or "",
                    "views": self._views_for(params["model"]),
                    "domain": params.get("domain") or [], "target": "current", "context": params.get("context") or {}}
        if kind == "report":
            opts = dict(options, report=params["report"])
            opts.update(params.get("options") or {})
            meta = self._report_meta()[params["report"]]
            return {"type": "ir.actions.client", "tag": "acc_report_heapdev", "name": meta["title"],
                    "params": {"report": params["report"], "options": opts}}
        dom = self._aml_domain(options, params.get("date_from"), params.get("date_to"))
        if params.get("date_before"):
            dom.append(("date", "<", params["date_before"]))
        if params.get("account_id"):
            dom.append(("account_id", "=", int(params["account_id"])))
        if params.get("account_ids"):
            dom.append(("account_id", "in", [int(a) for a in params["account_ids"]]))
        if params.get("partner_id"):
            dom.append(("partner_id", "=", int(params["partner_id"])))
        if params.get("journal_id"):
            dom.append(("journal_id", "=", int(params["journal_id"])))
        if params.get("tax_line_id"):
            dom.append(("tax_line_id", "=", int(params["tax_line_id"])))
        if params.get("tax_base_id"):
            dom.append(("tax_ids", "in", [int(params["tax_base_id"])]))
        if params.get("open_only"):
            dom.append(("reconciled", "=", False))
        return {
            "type": "ir.actions.act_window",
            "name": params.get("name") or _("Journal Items"),
            "res_model": "account.move.line",
            "views": self._views_for("account.move.line"),
            "domain": dom,
            "context": {"create": False},
            "target": "current",
        }

    @api.model
    def action_print_pdf(self, options):
        self._check_access()
        options = self._normalize(options)
        options["unfold_all"] = True
        return self.env.ref("accounting_reports_heapdev.action_report_acc_financial").report_action(self, data={"options": options})

    @api.model
    def get_pdf_values(self, options):
        self._check_access()
        self._reset_cache()
        options = self._normalize(options)
        options["unfold_all"] = True
        data = self._compute(options)
        return self._render_values(options, data, pdf=True)

    @api.model
    def export_xlsx(self, options):
        import xlsxwriter
        self._check_access()
        self._reset_cache()
        options = self._normalize(options)
        options["unfold_all"] = True
        data = self._compute(options)
        out = io.BytesIO()
        wb = xlsxwriter.Workbook(out, {"in_memory": True})
        ws = wb.add_worksheet((data["title"] or "Report")[:31])
        f_title = wb.add_format({"bold": True, "font_size": 15, "font_color": "#1f3b57"})
        f_sub = wb.add_format({"italic": True, "font_color": "#5a6b7b"})
        f_head = wb.add_format({"bold": True, "bg_color": "#1f3b57", "font_color": "#ffffff", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
        f_num = wb.add_format({"num_format": "#,##0.00"})
        f_text = wb.add_format({})
        f_sec = wb.add_format({"bold": True, "bg_color": "#e8eef5"})
        f_sec_num = wb.add_format({"bold": True, "bg_color": "#e8eef5", "num_format": "#,##0.00"})
        f_tot = wb.add_format({"bold": True, "top": 1})
        f_tot_num = wb.add_format({"bold": True, "top": 1, "num_format": "#,##0.00"})
        company = self._company()
        ws.write(0, 0, "%s  |  %s" % (data["title"], data.get("title_ar") or ""), f_title)
        ws.write(1, 0, "%s - %s" % (company.name, data.get("subtitle") or ""), f_sub)
        ws.write(2, 0, "%s: %s  |  %s" % (_("Currency"), self._currency().name, data.get("state_label") or ""), f_sub)
        row = 4
        ws.write(row, 0, "%s\n%s" % (data.get("first_col") or _("Account"), data.get("first_col_ar") or ar("Account")), f_head)
        for c, col in enumerate(data["columns"], 1):
            ws.write(row, c, "%s\n%s" % (col["label"], col.get("label_ar") or ""), f_head)
        ws.set_row(row, 32)
        ws.set_column(0, 0, 52)
        ws.set_column(1, max(len(data["columns"]), 1), 17)
        row += 1
        for line in data["lines"]:
            style = line["style"]
            if style in ("section", "subsection"):
                fn, ft = f_sec_num, f_sec
            elif style in ("total", "grand"):
                fn, ft = f_tot_num, f_tot
            else:
                fn, ft = f_num, f_text
            ws.write(row, 0, ("    " * line["level"]) + (line["name"] or ""), ft)
            for c, val in enumerate(line["values"], 1):
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    ws.write_number(row, c, val, fn)
                elif isinstance(val, date):
                    ws.write(row, c, self._fmt_date(val), ft)
                elif val not in (None, False, ""):
                    ws.write(row, c, str(val), ft)
                else:
                    ws.write_blank(row, c, None, ft)
            row += 1
        wb.close()
        fname = "%s_%s.xlsx" % ((data["title"] or "report").replace(" ", "_").replace("/", "-"), options["date_to"])
        return out.getvalue(), fname

    # ------------------------------------------------------------------ dispatcher
    def _compute(self, options):
        key = options["report"]
        method = getattr(self, "_report_%s" % key, None)
        if not method:
            raise UserError(_("Unknown report: %s") % key)
        meta = self._report_meta()[key]
        data = method(options)
        data.setdefault("title", meta["title"])
        data.setdefault("title_ar", meta.get("title_ar", ""))
        data.setdefault("key", key)
        data.setdefault("notes", [])
        data.setdefault("first_col", "")
        data.setdefault("first_col_ar", "")
        data.setdefault("blocks", [])
        data["blocks"] = [Markup(b) for b in data["blocks"]]
        data["extra_filters"] = [Markup(b) for b in data.get("extra_filters") or []]
        if "subtitle" not in data:
            if "asof" in meta.get("filters", []):
                data["subtitle"] = _("As of %s") % self._fmt_date(options["date_to"])
                data["subtitle_ar"] = "%s %s" % (ar("As of"), self._fmt_date(options["date_to"]))
            else:
                data["subtitle"] = _("From %s to %s") % (self._fmt_date(options["date_from"]), self._fmt_date(options["date_to"]))
                data["subtitle_ar"] = "%s %s %s %s" % (ar("From"), self._fmt_date(options["date_from"]), ar("To"), self._fmt_date(options["date_to"]))
        data["state_label"] = _("Posted entries only") if options["posted_only"] else _("All entries (incl. draft)")
        data["state_label_ar"] = ar("Posted entries only") if options["posted_only"] else ar("All entries (incl. draft)")
        if options.get("unfold_all"):
            for l in data["lines"]:
                l["folded"] = False
        else:
            hidden = set()
            for l in data["lines"]:
                if l.get("parent") in hidden:
                    l["cls"].append("o_acc_hidden")
                    hidden.add(l["id"])
                elif l.get("foldable") and l.get("folded"):
                    hidden.add(l["id"])
        return data

    # ------------------------------------------------------------------ section helper (P&L / BS)
    def _section_lines(self, prefix, sections, balances_per_col, sign, level, parent, cols, hide_zero, drill_dates, force=False):
        """sections: list of (key, name, name_ar, types). Returns (lines, totals per column)."""
        accounts = self._accounts()
        lines, grand = [], [0.0] * len(cols)
        for skey, sname, sname_ar, types in sections:
            acc_ids = sorted([a for a in accounts if accounts[a]["type"] in types], key=lambda a: accounts[a]["code"])
            sub, tot = [], [0.0] * len(cols)
            sid = "%s_%s" % (prefix, skey)
            for aid in acc_ids:
                vals = [sign * balances_per_col[i].get(aid, (0, 0, 0))[2] for i in range(len(cols))]
                if hide_zero and all(abs(v) < 0.005 for v in vals):
                    continue
                tot = [a + b for a, b in zip(tot, vals)]
                d = dict(drill_dates, type="aml", account_id=aid, name=accounts[aid]["display"])
                sub.append(self._line("%s_a%s" % (sid, aid), accounts[aid]["display"], vals, level + 1, "line", sid, d))
            if hide_zero and not sub and not force:
                continue
            lines.append(self._line(sid, sname, tot, level, "section", parent, None, sname_ar, True))
            lines.extend(sub)
            grand = [a + b for a, b in zip(grand, tot)]
        return lines, grand

    def _with_variance(self, data, nb_cols):
        if nb_cols == 2:
            data["columns"].append(self._col(_("Variance %"), ar("Variance %"), "pct"))
            for l in data["lines"]:
                vals = l["values"]
                if len(vals) == 2 and all(isinstance(v, (int, float)) for v in vals):
                    cur, prev = vals
                    vals.append("%+.1f%%" % ((cur - prev) / abs(prev) * 100.0) if abs(prev) > 0.005 else "")
                else:
                    vals.append("")
        return data

    # ------------------------------------------------------------------ Profit & Loss
    def _report_pl(self, options):
        cols = self._periods(options)
        pl_ids = self._accounts_of(PL_TYPES)
        bals = [self._balances(options, date_from=df, date_to=dt, accounts=pl_ids) for df, dt in cols]
        hz = options["hide_zero"]
        dd = {"date_from": options["date_from"], "date_to": options["date_to"]}
        inc_l, inc = self._section_lines("pl", [("income", _("Operating Income"), ar("Operating Income"), ["income"])], bals, -1, 0, None, cols, hz, dd, True)
        cogs_l, cogs = self._section_lines("pl", [("cogs", _("Cost of Revenue"), ar("Cost of Revenue"), ["expense_direct_cost"])], bals, 1, 0, None, cols, hz, dd, True)
        gross = [a - b for a, b in zip(inc, cogs)]
        oth_l, oth = self._section_lines("pl", [("other", _("Other Income"), ar("Other Income"), ["income_other"])], bals, -1, 0, None, cols, hz, dd)
        exp_l, exp = self._section_lines("pl", [("expense", _("Operating Expenses"), ar("Operating Expenses"), ["expense"])], bals, 1, 0, None, cols, hz, dd, True)
        dep_l, dep = self._section_lines("pl", [("dep", _("Depreciation"), ar("Depreciation"), ["expense_depreciation"])], bals, 1, 0, None, cols, hz, dd)
        net = [g + o - e - d for g, o, e, d in zip(gross, oth, exp, dep)]
        lines = inc_l + cogs_l
        lines.append(self._line("pl_gross", _("Gross Profit"), gross, 0, "total", None, None, ar("Gross Profit")))
        lines += oth_l + exp_l + dep_l
        lines.append(self._line("pl_net", _("Net Profit"), net, 0, "grand", None, None, ar("Net Profit")))
        data = {"columns": [self._col(self._period_label(df, dt)) for df, dt in cols], "lines": lines,
                "first_col": _("Account"), "first_col_ar": ar("Account"),
                "kpis": {"income": inc[0] + oth[0], "expense": cogs[0] + exp[0] + dep[0], "net": net[0], "gross": gross[0]}}
        return self._with_variance(data, len(cols))

    # ------------------------------------------------------------------ Balance Sheet
    def _report_bs(self, options):
        dt0 = self._to_date(options["date_to"])
        cols = [(None, p[1]) for p in self._periods(options)]
        accounts = self._accounts()
        bs_ids = [a for a in accounts if accounts[a]["type"] not in PL_TYPES + ("off_balance",)]
        bals = [self._balances(options, date_to=dt, accounts=bs_ids) for _df, dt in cols]
        hz = options["hide_zero"]
        dd = {"date_to": options["date_to"]}
        lines = []
        cur_l, cur = self._section_lines("bs_ca", [
            ("cash", _("Bank and Cash Accounts"), ar("Bank and Cash Accounts"), ["asset_cash"]),
            ("rec", _("Receivables"), ar("Receivables"), ["asset_receivable"]),
            ("cur", _("Other Current Assets"), ar("Other Current Assets"), ["asset_current"]),
            ("pre", _("Prepayments"), ar("Prepayments"), ["asset_prepayments"]),
        ], bals, 1, 2, "bs_ca", cols, hz, dd)
        fix_l, fix = self._section_lines("bs", [("fa", _("Fixed Assets"), ar("Fixed Assets"), ["asset_fixed"])], bals, 1, 1, "bs_assets", cols, hz, dd)
        nca_l, nca = self._section_lines("bs", [("nca", _("Non-current Assets"), ar("Non-current Assets"), ["asset_non_current"])], bals, 1, 1, "bs_assets", cols, hz, dd)
        assets = [a + b + c for a, b, c in zip(cur, fix, nca)]
        lines.append(self._line("bs_assets", _("Assets"), assets, 0, "section", None, None, ar("Assets"), True))
        lines.append(self._line("bs_ca", _("Current Assets"), cur, 1, "section", "bs_assets", None, ar("Current Assets"), True))
        lines += cur_l + fix_l + nca_l
        lines.append(self._line("bs_total_assets", _("Total Assets"), assets, 0, "grand", None, None, ar("Total Assets")))
        cl_l, cl = self._section_lines("bs_cl", [
            ("cl", _("Other Current Liabilities"), ar("Other Current Liabilities"), ["liability_current"]),
            ("pay", _("Payables"), ar("Payables"), ["liability_payable"]),
            ("cc", _("Credit Cards"), ar("Credit Cards"), ["liability_credit_card"]),
        ], bals, -1, 2, "bs_cl", cols, hz, dd)
        ncl_l, ncl = self._section_lines("bs", [("ncl", _("Non-current Liabilities"), ar("Non-current Liabilities"), ["liability_non_current"])], bals, -1, 1, "bs_liab", cols, hz, dd)
        liab = [a + b for a, b in zip(cl, ncl)]
        lines.append(self._line("bs_liab", _("Liabilities"), liab, 0, "section", None, None, ar("Liabilities"), True))
        lines.append(self._line("bs_cl", _("Current Liabilities"), cl, 1, "section", "bs_liab", None, ar("Current Liabilities"), True))
        lines += cl_l + ncl_l
        lines.append(self._line("bs_total_liab", _("Total Liabilities"), liab, 0, "total", None, None, ar("Total Liabilities")))
        unaff_ids = self._accounts_of(["equity_unaffected"])
        pl_ids = self._accounts_of(PL_TYPES)
        cye, pye = [], []
        for _df, dt in cols:
            fy_start = self._fy(dt)[0]
            cur_pl = self._balances(options, date_from=fy_start, date_to=dt, accounts=pl_ids)
            prev_pl = self._balances(options, date_before=fy_start, accounts=pl_ids)
            unaff = self._balances(options, date_to=dt, accounts=unaff_ids)
            cye.append(-sum(v[2] for v in cur_pl.values()))
            pye.append(-sum(v[2] for v in prev_pl.values()) - sum(v[2] for v in unaff.values()))
        eq_l, eq = self._section_lines("bs", [("re", _("Retained Earnings"), ar("Retained Earnings"), ["equity"])], bals, -1, 1, "bs_equity", cols, hz, dd)
        unalloc = [a + b for a, b in zip(cye, pye)]
        equity = [a + b for a, b in zip(eq, unalloc)]
        lines.append(self._line("bs_equity", _("Equity"), equity, 0, "section", None, None, ar("Equity"), True))
        lines.append(self._line("bs_unalloc", _("Unallocated Earnings"), unalloc, 1, "section", "bs_equity", None, ar("Unallocated Earnings"), True))
        fy0 = fields.Date.to_string(self._fy(dt0)[0])
        lines.append(self._line("bs_cye", _("Current Year Earnings"), cye, 2, "line", "bs_unalloc",
                                {"type": "aml", "account_ids": pl_ids, "date_from": fy0, "date_to": options["date_to"], "name": _("Current Year Earnings")}, ar("Current Year Earnings")))
        lines.append(self._line("bs_pye", _("Previous Years Unallocated Earnings"), pye, 2, "line", "bs_unalloc",
                                {"type": "aml", "account_ids": pl_ids + unaff_ids, "date_before": fy0, "name": _("Previous Years Unallocated Earnings")}, ar("Previous Years Unallocated Earnings")))
        lines += eq_l
        lines.append(self._line("bs_total_eq", _("Total Equity"), equity, 0, "total", None, None, ar("Total Equity")))
        total = [a + b for a, b in zip(liab, equity)]
        lines.append(self._line("bs_total_le", _("Liabilities + Equity"), total, 0, "grand", None, None, ar("Liabilities + Equity")))
        data = {"columns": [self._col(_("As of %s") % self._fmt_date(dt)) for _df, dt in cols], "lines": lines,
                "first_col": _("Account"), "first_col_ar": ar("Account"),
                "kpis": {"assets": assets[0], "liabilities": liab[0], "equity": equity[0], "balanced": abs(assets[0] - total[0]) < 0.01}}
        if abs(assets[0] - total[0]) > 0.01:
            data["notes"] = [_("Warning: total assets differ from liabilities + equity by %s. Check accounts with unusual types.") % self._fmt(assets[0] - total[0])]
        return self._with_variance(data, len(cols))

    # ------------------------------------------------------------------ Cash Flow (direct method, allocation of liquidity moves on counterpart accounts)
    def _report_cf(self, options):
        accounts = self._accounts()
        liq = self._accounts_of(["asset_cash"])
        df, dt = options["date_from"], options["date_to"]
        where, params = self._where(options, date_from=df, date_to=dt, accounts=liq, analytic=False, partners=False)
        _acc_flush(self.env)
        self.env.cr.execute("""
            WITH liq AS (
                SELECT aml.move_id, SUM(aml.balance) AS amt FROM account_move_line aml WHERE %s GROUP BY aml.move_id
            ), cp AS (
                SELECT l.move_id, l.account_id, l.balance FROM account_move_line l JOIN liq ON liq.move_id = l.move_id
                WHERE l.account_id IS NOT NULL AND NOT (l.account_id = ANY(%%s))
            ), tot AS (SELECT move_id, SUM(balance) AS s FROM cp GROUP BY move_id)
            SELECT cp.account_id, SUM(liq.amt * cp.balance / tot.s)
            FROM cp JOIN liq ON liq.move_id = cp.move_id JOIN tot ON tot.move_id = cp.move_id
            WHERE tot.s <> 0 GROUP BY cp.account_id
        """ % where, params + [liq or [0]])
        flows = {r[0]: r[1] or 0.0 for r in self.env.cr.fetchall()}
        groups = OrderedDict([
            ("op_in", (_("Cash received from customers and other income"), ar("Cash received from customers and other income"), ("asset_receivable", "income", "income_other"))),
            ("op_out", (_("Cash paid to suppliers, employees and expenses"), ar("Cash paid to suppliers, employees and expenses"),
                        ("liability_payable", "expense", "expense_direct_cost", "expense_depreciation", "liability_current", "liability_credit_card", "asset_current", "asset_prepayments"))),
            ("inv", (_("Cash flows from investing activities"), ar("Cash flows from investing activities"), ("asset_fixed", "asset_non_current"))),
            ("fin", (_("Cash flows from financing activities"), ar("Cash flows from financing activities"), ("equity", "equity_unaffected", "liability_non_current"))),
            ("oth", (_("Cash flows from unclassified activities"), ar("Cash flows from unclassified activities"), ("off_balance", "asset_cash"))),
        ])
        sub, totals = {}, {}
        for gk, (_gname, _gname_ar, types) in groups.items():
            items = sorted([(aid, amt) for aid, amt in flows.items() if accounts.get(aid, {}).get("type") in types and abs(amt) > 0.005], key=lambda x: accounts[x[0]]["code"])
            sub[gk] = items
            totals[gk] = sum(a for _x, a in items)
        opening = sum(v[2] for v in self._balances(options, date_before=df, accounts=liq, analytic=False, partners=False).values())
        lines = []
        dd = {"date_from": df, "date_to": dt}
        op_total = totals["op_in"] + totals["op_out"]
        lines.append(self._line("cf_op", _("Cash flows from operating activities"), [op_total], 0, "section", None, None, ar("Cash flows from operating activities"), True))
        for gk in ("op_in", "op_out"):
            gname, gname_ar = groups[gk][0], groups[gk][1]
            lines.append(self._line("cf_" + gk, gname, [totals[gk]], 1, "subsection", "cf_op", None, gname_ar, True))
            for aid, amt in sub[gk]:
                lines.append(self._line("cf_%s_%s" % (gk, aid), accounts[aid]["display"], [amt], 2, "line", "cf_" + gk, dict(dd, type="aml", account_id=aid, name=accounts[aid]["display"])))
        lines.append(self._line("cf_op_total", _("Net cash from operating activities"), [op_total], 0, "total", None, None, ar("Net cash from operating activities")))
        for gk in ("inv", "fin", "oth"):
            if gk == "oth" and not sub[gk]:
                continue
            gname, gname_ar = groups[gk][0], groups[gk][1]
            lines.append(self._line("cf_" + gk, gname, [totals[gk]], 0, "section", None, None, gname_ar, True))
            for aid, amt in sub[gk]:
                lines.append(self._line("cf_%s_%s" % (gk, aid), accounts[aid]["display"], [amt], 1, "line", "cf_" + gk, dict(dd, type="aml", account_id=aid, name=accounts[aid]["display"])))
        net = sum(totals.values())
        lines.append(self._line("cf_net", _("Net increase in cash and cash equivalents"), [net], 0, "total", None, None, ar("Net increase in cash and cash equivalents")))
        lines.append(self._line("cf_open", _("Cash and cash equivalents, beginning of period"), [opening], 0, "line", None,
                                {"type": "aml", "account_ids": liq, "date_before": df, "name": _("Opening cash")}, ar("Cash and cash equivalents, beginning of period")))
        lines.append(self._line("cf_close", _("Cash and cash equivalents, end of period"), [opening + net], 0, "grand", None,
                                {"type": "aml", "account_ids": liq, "date_to": dt, "name": _("Closing cash")}, ar("Cash and cash equivalents, end of period")))
        return {"columns": [self._col(self._period_label(self._to_date(df), self._to_date(dt)))], "lines": lines,
                "first_col": _("Account"), "first_col_ar": ar("Account"),
                "kpis": {"net": net, "opening": opening, "closing": opening + net}}

    # ------------------------------------------------------------------ General Ledger
    def _initial_balances(self, options, partners=True):
        """Initial balance per account: balance sheet accounts from the beginning, P&L accounts from the fiscal year start.
        Returns (dict account -> (debit, credit, balance), undistributed P&L of previous years)."""
        df = self._to_date(options["date_from"])
        fy_start = self._fy(df)[0]
        pl_ids = set(self._accounts_of(PL_TYPES))
        before = self._balances(options, date_before=df, partners=partners)
        res = {aid: v for aid, v in before.items() if aid not in pl_ids}
        pl_this_fy = self._balances(options, date_from=fy_start, date_before=df, accounts=list(pl_ids), partners=partners) if fy_start < df else {}
        res.update(pl_this_fy)
        undistributed = sum(v[2] for aid, v in before.items() if aid in pl_ids) - sum(v[2] for v in pl_this_fy.values())
        return res, undistributed

    def _move_lines(self, options, order="aml.account_id, aml.date, aml.id", limit=None, **kw):
        where, params = self._where(options, **kw)
        q = """SELECT aml.id, aml.date, aml.account_id, aml.move_id, am.name, COALESCE(aml.name, ''), aml.partner_id,
                      COALESCE(p.name, ''), aml.debit, aml.credit, aml.balance, aj.code, aml.journal_id, aml.date_maturity, COALESCE(am.ref, '')
               FROM account_move_line aml
               JOIN account_move am ON am.id = aml.move_id
               JOIN account_journal aj ON aj.id = aml.journal_id
               LEFT JOIN res_partner p ON p.id = aml.partner_id
               WHERE %s ORDER BY %s %s""" % (where, order, "LIMIT %d" % limit if limit else "")
        _acc_flush(self.env)
        self.env.cr.execute(q, params)
        keys = ["id", "date", "account_id", "move_id", "move_name", "label", "partner_id", "partner", "debit", "credit", "balance", "jcode", "journal_id", "date_maturity", "ref"]
        rows = [dict(zip(keys, r)) for r in self.env.cr.fetchall()]
        for r in rows:
            for k in ("jcode", "label", "partner"):
                if isinstance(r[k], dict):
                    r[k] = r[k].get(self.env.lang or "en_US") or r[k].get("en_US") or next(iter(r[k].values()), "")
        return rows

    def _report_gl(self, options):
        accounts = self._accounts()
        df, dt = options["date_from"], options["date_to"]
        init, _undist = self._initial_balances(options)
        rows = self._move_lines(options, date_from=df, date_to=dt)
        by_acc = defaultdict(list)
        for r in rows:
            by_acc[r["account_id"]].append(r)
        acc_ids = sorted(set(by_acc) | {a for a, v in init.items() if abs(v[2]) > 0.005}, key=lambda a: accounts.get(a, {}).get("code", ""))
        lines = []
        td = tc = 0.0
        for aid in acc_ids:
            a = accounts.get(aid, {"display": str(aid), "code": ""})
            ib = init.get(aid, (0.0, 0.0, 0.0))
            items = by_acc.get(aid, [])
            deb = ib[0] + sum(r["debit"] for r in items)
            cre = ib[1] + sum(r["credit"] for r in items)
            bal = ib[2] + sum(r["balance"] for r in items)
            td += deb
            tc += cre
            lid = "gl_a%s" % aid
            lines.append(self._line(lid, a["display"], ["", "", "", "", deb, cre, bal], 0, "section", None,
                                    {"type": "aml", "account_id": aid, "date_from": df, "date_to": dt, "name": a["display"]}, foldable=True))
            lines[-1]["folded"] = True
            run = ib[2]
            lines.append(self._line(lid + "_init", _("Initial Balance"), ["", "", "", "", ib[0], ib[1], ib[2]], 1, "detail", lid, None, ar("Initial Balance")))
            for r in items[:3000]:
                run += r["balance"]
                lines.append(self._line("gl_l%s" % r["id"], self._fmt_date(r["date"]), [r["jcode"], r["move_name"], r["partner"], r["label"], r["debit"], r["credit"], run], 1, "detail", lid,
                                        {"type": "move", "move_id": r["move_id"]}))
            if len(items) > 3000:
                lines.append(self._line(lid + "_more", _("%s more lines: export to XLSX to see all of them") % (len(items) - 3000), ["", "", "", "", "", "", ""], 1, "detail", lid))
        lines.append(self._line("gl_total", _("Total"), ["", "", "", "", td, tc, td - tc], 0, "grand", None, None, ar("Total")))
        cols = [self._col(_("JRNL"), ar("JRNL"), "text"), self._col(_("Entry"), ar("Entry"), "text"), self._col(_("Partner"), ar("Partner"), "text"),
                self._col(_("Label"), ar("Label"), "text"), self._col(_("Debit"), ar("Debit")), self._col(_("Credit"), ar("Credit")), self._col(_("Balance"), ar("Balance"))]
        return {"columns": cols, "lines": lines, "first_col": _("Account / Date"), "first_col_ar": ar("Account")}

    # ------------------------------------------------------------------ Trial Balance
    def _report_tb(self, options):
        accounts = self._accounts()
        df, dt = options["date_from"], options["date_to"]
        init, undist = self._initial_balances(options)
        per = self._balances(options, date_from=df, date_to=dt)
        acc_ids = sorted(set(per) | {a for a, v in init.items() if abs(v[2]) > 0.005}, key=lambda a: accounts.get(a, {}).get("code", ""))
        lines = []
        tot = [0.0, 0.0, 0.0, 0.0]
        for aid in acc_ids:
            a = accounts.get(aid, {"display": str(aid)})
            ib = init.get(aid, (0, 0, 0))[2]
            d, c = per.get(aid, (0, 0, 0))[:2]
            vals = [ib, d, c, ib + d - c]
            if options["hide_zero"] and all(abs(v) < 0.005 for v in vals):
                continue
            tot = [x + y for x, y in zip(tot, vals)]
            lines.append(self._line("tb_a%s" % aid, a["display"], vals, 0, "line", None, {"type": "aml", "account_id": aid, "date_from": df, "date_to": dt, "name": a["display"]}))
        if abs(undist) > 0.005:
            tot[0] += undist
            tot[3] += undist
            lines.append(self._line("tb_undist", _("Undistributed Profits/Losses"), [undist, 0.0, 0.0, undist], 0, "line", None, None, ar("Undistributed Profits/Losses")))
        lines.append(self._line("tb_total", _("Total"), tot, 0, "grand", None, None, ar("Total")))
        cols = [self._col(_("Initial Balance"), ar("Initial Balance")), self._col(_("Debit"), ar("Debit")), self._col(_("Credit"), ar("Credit")), self._col(_("Ending Balance"), ar("Ending Balance"))]
        return {"columns": cols, "lines": lines, "first_col": _("Account"), "first_col_ar": ar("Account"),
                "kpis": {"debit": tot[1], "credit": tot[2], "balanced": abs(tot[1] - tot[2]) < 0.01}}

    # ------------------------------------------------------------------ Partner Ledger
    def _partner_accounts(self, kind):
        types = {"receivable": ["asset_receivable"], "payable": ["liability_payable"], "both": ["asset_receivable", "liability_payable"]}[kind]
        return self._accounts_of(types)

    def _report_partner_ledger(self, options):
        df, dt = options["date_from"], options["date_to"]
        accs = self._partner_accounts(options["account_kind"])
        where_i, params_i = self._where(options, date_before=df, accounts=accs)
        _acc_flush(self.env)
        self.env.cr.execute("SELECT aml.partner_id, SUM(aml.debit), SUM(aml.credit), SUM(aml.balance) FROM account_move_line aml WHERE %s GROUP BY aml.partner_id" % where_i, params_i)
        init = {r[0]: (r[1] or 0.0, r[2] or 0.0, r[3] or 0.0) for r in self.env.cr.fetchall()}
        rows = self._move_lines(options, date_from=df, date_to=dt, accounts=accs, order="aml.partner_id, aml.date, aml.id")
        by_p = OrderedDict()
        for r in rows:
            by_p.setdefault(r["partner_id"], []).append(r)
        pids = list(by_p) + [p for p, v in init.items() if p not in by_p and abs(v[2]) > 0.005]
        names = {p.id: p.name or p.display_name for p in self.env["res.partner"].browse([p for p in pids if p]).exists()}
        pids.sort(key=lambda p: (p is None, (names.get(p) or "").lower()))
        lines, td, tc = [], 0.0, 0.0
        for pid in pids:
            ib = init.get(pid, (0.0, 0.0, 0.0))
            items = by_p.get(pid, [])
            deb = ib[0] + sum(r["debit"] for r in items)
            cre = ib[1] + sum(r["credit"] for r in items)
            td += deb
            tc += cre
            lid = "pl_p%s" % (pid or 0)
            pname = names.get(pid) or _("Unknown Partner")
            lines.append(self._line(lid, pname, ["", "", "", deb, cre, deb - cre], 0, "section", None,
                                    {"type": "aml", "partner_id": pid, "account_ids": accs, "date_from": df, "date_to": dt, "name": pname} if pid else None, foldable=True))
            lines[-1]["folded"] = True
            run = ib[2]
            lines.append(self._line(lid + "_init", _("Initial Balance"), ["", "", "", ib[0], ib[1], run], 1, "detail", lid, None, ar("Initial Balance")))
            for r in items:
                run += r["balance"]
                lines.append(self._line("pl_l%s" % r["id"], self._fmt_date(r["date"]), [r["jcode"], r["move_name"], self._fmt_date(r["date_maturity"]), r["debit"], r["credit"], run], 1, "detail", lid,
                                        {"type": "move", "move_id": r["move_id"]}))
        lines.append(self._line("pl_total", _("Total"), ["", "", "", td, tc, td - tc], 0, "grand", None, None, ar("Total")))
        cols = [self._col(_("JRNL"), ar("JRNL"), "text"), self._col(_("Entry"), ar("Entry"), "text"), self._col(_("Due Date"), ar("Due Date"), "text"),
                self._col(_("Debit"), ar("Debit")), self._col(_("Credit"), ar("Credit")), self._col(_("Balance"), ar("Balance"))]
        return {"columns": cols, "lines": lines, "first_col": _("Partner / Date"), "first_col_ar": ar("Partner")}

    # ------------------------------------------------------------------ Journal Audit
    def _report_journal_audit(self, options):
        accounts = self._accounts()
        df, dt = options["date_from"], options["date_to"]
        rows = self._move_lines(options, date_from=df, date_to=dt, order="aml.journal_id, aml.date, aml.move_id, aml.id")
        lines, td, tc = [], 0.0, 0.0
        journals = OrderedDict()
        for r in rows:
            journals.setdefault(r["journal_id"], []).append(r)
        jrecs = self.env["account.journal"].browse(list(journals))
        jnames = {j.id: "%s (%s)" % (j.name, j.code) for j in jrecs}
        for jid in sorted(journals, key=lambda j: jnames.get(j, "")):
            items = journals[jid]
            jd = sum(r["debit"] for r in items)
            jc = sum(r["credit"] for r in items)
            td += jd
            tc += jc
            jl = "ja_j%s" % jid
            lines.append(self._line(jl, jnames.get(jid, ""), ["", "", "", jd, jc], 0, "section", None,
                                    {"type": "aml", "journal_id": jid, "date_from": df, "date_to": dt, "name": jnames.get(jid, "")}, foldable=True))
            moves = OrderedDict()
            for r in items:
                moves.setdefault(r["move_id"], []).append(r)
            for mid, mlines in moves.items():
                first = mlines[0]
                ml = "ja_m%s" % mid
                lines.append(self._line(ml, "%s  %s" % (self._fmt_date(first["date"]), first["move_name"] or ""),
                                        [first["partner"], first["ref"], "", sum(x["debit"] for x in mlines), sum(x["credit"] for x in mlines)], 1, "subsection", jl,
                                        {"type": "move", "move_id": mid}, foldable=True))
                lines[-1]["folded"] = True
                for r in mlines:
                    lines.append(self._line("ja_l%s" % r["id"], accounts.get(r["account_id"], {}).get("display", ""), ["", "", r["label"], r["debit"], r["credit"]], 2, "detail", ml, {"type": "move", "move_id": mid}))
        lines.append(self._line("ja_total", _("Total"), ["", "", "", td, tc], 0, "grand", None, None, ar("Total")))
        cols = [self._col(_("Partner"), ar("Partner"), "text"), self._col(_("Reference"), ar("Reference"), "text"), self._col(_("Label"), ar("Label"), "text"),
                self._col(_("Debit"), ar("Debit")), self._col(_("Credit"), ar("Credit"))]
        return {"columns": cols, "lines": lines, "first_col": _("Journal / Entry / Account"), "first_col_ar": ar("Journal")}

    # ------------------------------------------------------------------ Aged Receivable / Payable
    def _aged_rows(self, options, kind):
        as_of = options["date_to"]
        accs = self._partner_accounts(kind)
        where, params = self._where(options, date_to=as_of, accounts=accs, journals=False, analytic=False)
        _acc_flush(self.env)
        self.env.cr.execute("""
            SELECT aml.id, aml.partner_id, COALESCE(p.name, ''), aml.move_id, am.name, aml.date, COALESCE(aml.date_maturity, aml.date),
                   aml.balance
                   - COALESCE((SELECT SUM(pr.amount) FROM account_partial_reconcile pr WHERE pr.debit_move_id = aml.id AND pr.max_date <= %%s), 0)
                   + COALESCE((SELECT SUM(pr.amount) FROM account_partial_reconcile pr WHERE pr.credit_move_id = aml.id AND pr.max_date <= %%s), 0) AS residual
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN res_partner p ON p.id = aml.partner_id
            WHERE %s
        """ % where, [as_of, as_of] + params)
        rows = []
        for r in self.env.cr.fetchall():
            if abs(r[7] or 0) > 0.005:
                rows.append({"id": r[0], "partner_id": r[1], "partner": r[2], "move_id": r[3], "move_name": r[4], "date": r[5], "due": r[6], "residual": r[7]})
        return rows

    def _report_aged_receivable(self, options):
        return self._report_aged(options, "receivable")

    def _report_aged_payable(self, options):
        return self._report_aged(options, "payable")

    def _aged_bucket(self, days):
        if days <= 0:
            return 0
        if days <= 30:
            return 1
        if days <= 60:
            return 2
        if days <= 90:
            return 3
        if days <= 120:
            return 4
        return 5

    def _report_aged(self, options, kind):
        as_of = self._to_date(options["date_to"])
        sign = 1 if kind == "receivable" else -1
        rows = self._aged_rows(options, kind)
        accs = self._partner_accounts(kind)
        by_p = OrderedDict()
        for r in sorted(rows, key=lambda x: ((x["partner"] or "").lower(), x["due"])):
            by_p.setdefault(r["partner_id"], []).append(r)
        lines = []
        grand = [0.0] * 7
        for pid, items in by_p.items():
            ptot = [0.0] * 7
            sub = []
            pl = "ag_p%s" % (pid or 0)
            for r in items:
                vals = [0.0] * 7
                amt = sign * r["residual"]
                vals[self._aged_bucket((as_of - self._to_date(r["due"])).days)] = amt
                vals[6] = amt
                ptot = [a + b for a, b in zip(ptot, vals)]
                sub.append(self._line("ag_l%s" % r["id"], r["move_name"] or "", [self._fmt_date(r["due"])] + vals, 1, "detail", pl, {"type": "move", "move_id": r["move_id"]}))
            grand = [a + b for a, b in zip(grand, ptot)]
            pname = items[0]["partner"] or _("Unknown Partner")
            lines.append(self._line(pl, pname, [""] + ptot, 0, "section", None,
                                    {"type": "aml", "partner_id": pid, "account_ids": accs, "date_to": options["date_to"], "open_only": True, "name": pname} if pid else None, foldable=True))
            lines[-1]["folded"] = True
            lines += sub
        lines.append(self._line("ag_total", _("Total"), [""] + grand, 0, "grand", None, None, ar("Total")))
        cols = [self._col(_("Due Date"), ar("Due Date"), "text"), self._col(_("Not Due"), ar("Not Due")), self._col(_("1-30"), "1-30"), self._col(_("31-60"), "31-60"),
                self._col(_("61-90"), "61-90"), self._col(_("91-120"), "91-120"), self._col(_("Older"), ar("Older")), self._col(_("Total"), ar("Total"))]
        return {"columns": cols, "lines": lines, "first_col": _("Partner / Entry"), "first_col_ar": ar("Partner"),
                "kpis": {"total": grand[6], "overdue": sum(grand[1:6]), "buckets": grand[:6]}}

    # ------------------------------------------------------------------ Tax report (UAE FTA 201 / KSA ZATCA friendly summary)
    def _report_tax(self, options):
        df, dt = options["date_from"], options["date_to"]
        where, params = self._where(options, date_from=df, date_to=dt, analytic=False, partners=False)
        _acc_flush(self.env)
        self.env.cr.execute("SELECT aml.tax_line_id, SUM(aml.balance) FROM account_move_line aml WHERE %s AND aml.tax_line_id IS NOT NULL GROUP BY aml.tax_line_id" % where, params)
        tax_amt = dict(self.env.cr.fetchall())
        _acc_flush(self.env)
        self.env.cr.execute("""SELECT rel.account_tax_id, SUM(aml.balance) FROM account_move_line aml
                               JOIN account_move_line_account_tax_rel rel ON rel.account_move_line_id = aml.id
                               WHERE %s GROUP BY rel.account_tax_id""" % where, params)
        base_amt = dict(self.env.cr.fetchall())
        taxes = self.env["account.tax"].with_context(active_test=False).browse(list(set(tax_amt) | set(base_amt))).exists()
        lines = []
        summary = {"std_sales": [0.0, 0.0], "zero_sales": [0.0, 0.0], "exempt_sales": [0.0, 0.0], "std_purch": [0.0, 0.0], "other_purch": [0.0, 0.0]}
        out_tax = in_tax = 0.0
        for use, title, title_ar, sign in (("sale", _("Sales (Output VAT)"), ar("Sales (Output VAT)"), -1),
                                           ("purchase", _("Purchases (Input VAT)"), ar("Purchases (Input VAT)"), 1)):
            group = taxes.filtered(lambda t: t.type_tax_use == use).sorted(lambda t: (t.sequence, t.id))
            sec_base = sec_tax = 0.0
            sub = []
            for tax in group:
                base = sign * (base_amt.get(tax.id) or 0.0)
                amt = sign * (tax_amt.get(tax.id) or 0.0)
                sec_base += base
                sec_tax += amt
                rate = ("%g%%" % tax.amount) if tax.amount_type == "percent" else ""
                label = ("%s (%s)" % (tax.name, rate)) if rate and rate not in (tax.name or "") else tax.name
                sub.append(self._line("tx_%s" % tax.id, label, [base, amt], 1, "line", "tx_" + use,
                                      {"type": "aml", "tax_line_id": tax.id, "date_from": df, "date_to": dt, "name": tax.name}))
                tname = (tax.name or "").lower()
                is_exempt = "exempt" in tname or "معف" in tname
                if use == "sale":
                    k = "std_sales" if tax.amount else ("exempt_sales" if is_exempt else "zero_sales")
                else:
                    k = "std_purch" if tax.amount else "other_purch"
                summary[k][0] += base
                summary[k][1] += amt
            lines.append(self._line("tx_" + use, title, [sec_base, sec_tax], 0, "section", None, None, title_ar, True))
            lines += sub
            if use == "sale":
                out_tax = sec_tax
            else:
                in_tax = sec_tax
        lines.append(self._line("tx_summary", _("VAT Return Summary"), ["", ""], 0, "section", None, None, ar("VAT Return Summary"), True))
        tot_sales = [summary["std_sales"][i] + summary["zero_sales"][i] + summary["exempt_sales"][i] for i in (0, 1)]
        tot_purch = [summary["std_purch"][i] + summary["other_purch"][i] for i in (0, 1)]
        for k, name, name_ar, vals in (
                ("1", _("Standard rated supplies"), ar("Standard rated supplies"), summary["std_sales"]),
                ("2", _("Zero-rated supplies"), ar("Zero-rated supplies"), summary["zero_sales"]),
                ("3", _("Exempt supplies"), ar("Exempt supplies"), summary["exempt_sales"]),
                ("4", _("Total sales"), ar("Total sales"), tot_sales),
                ("5", _("Standard rated expenses"), ar("Standard rated expenses"), summary["std_purch"]),
                ("6", _("Other expenses (zero-rated / exempt)"), ar("Other expenses (zero-rated / exempt)"), summary["other_purch"]),
                ("7", _("Total purchases"), ar("Total purchases"), tot_purch)):
            lines.append(self._line("tx_box" + k, "%s. %s" % (k, name), list(vals), 1, "total" if k in ("4", "7") else "line", "tx_summary", None, name_ar))
        lines.append(self._line("tx_out", _("Output VAT due"), ["", out_tax], 0, "line", None, None, ar("Output VAT due")))
        lines.append(self._line("tx_in", _("Input VAT recoverable"), ["", in_tax], 0, "line", None, None, ar("Input VAT recoverable")))
        lines.append(self._line("tx_net", _("Net VAT payable / (refundable)"), ["", out_tax - in_tax], 0, "grand", None, None, ar("Net VAT payable / (refundable)")))
        cols = [self._col(_("Net Amount"), ar("Net Amount")), self._col(_("Tax"), ar("Tax"))]
        return {"columns": cols, "lines": lines, "first_col": _("Tax"), "first_col_ar": ar("Tax"),
                "kpis": {"output": out_tax, "input": in_tax, "net": out_tax - in_tax}}

# -*- coding: utf-8 -*-
from collections import OrderedDict

from odoo import _, models


class AccReportEngineAssets(models.AbstractModel):
    _inherit = "acc.report.engine"

    def _report_meta(self):
        res = super()._report_meta()
        res["assets"] = {"title": _("Depreciation Schedule"), "title_ar": "جدول الإهلاك", "filters": ["date"]}
        return res

    def _report_assets(self, options):
        df, dt = self._to_date(options["date_from"]), self._to_date(options["date_to"])
        assets = self.env["acc.asset"].search([("company_id", "=", self._company().id), ("asset_type", "=", "asset"),
                                               ("state", "in", ("open", "close")), ("date", "<=", dt)], order="category_id, date, id")
        cols = [self._col(_("Acquisition"), "تاريخ الاقتناء", "text"), self._col(_("Gross Value"), "القيمة الإجمالية"),
                self._col(_("Opening Depreciation"), "الإهلاك الافتتاحي"), self._col(_("Depreciation"), "إهلاك الفترة"),
                self._col(_("Disposals"), "الاستبعادات"), self._col(_("Closing Depreciation"), "الإهلاك المتراكم"),
                self._col(_("Book Value"), "القيمة الدفترية")]
        groups = OrderedDict()
        for asset in assets:
            if asset.disposal_date and asset.disposal_date < df:
                continue
            opening = asset.already_depreciated
            period = 0.0
            for l in asset.line_ids:
                if not l.move_id or l.move_id.state != "posted":
                    continue
                if l.date < df:
                    opening += l.amount
                elif l.date <= dt:
                    period += l.amount
            disposed = bool(asset.disposal_date and df <= asset.disposal_date <= dt)
            disposal = -(opening + period) if disposed else 0.0
            closing = opening + period + disposal
            gross = asset.value
            book = 0.0 if disposed else gross - closing
            vals = [self._fmt_date(asset.date), gross, opening, period, disposal, closing, book]
            groups.setdefault(asset.category_id, []).append((asset, vals))
        lines, grand = [], [0.0] * 6
        for cat, rows in groups.items():
            tot = [0.0] * 6
            sub = []
            for asset, vals in rows:
                tot = [a + b for a, b in zip(tot, vals[1:])]
                sub.append(self._line("ast_%s" % asset.id, "%s%s" % (asset.name, " [%s]" % asset.code if asset.code else ""), vals, 1, "line",
                                      "astc_%s" % cat.id, {"type": "record", "model": "acc.asset", "res_id": asset.id, "name": asset.name}))
            lines.append(self._line("astc_%s" % cat.id, cat.name, [""] + tot, 0, "section", None, None, "", True))
            lines.extend(sub)
            grand = [a + b for a, b in zip(grand, tot)]
        if lines:
            lines.append(self._line("ast_total", _("Total"), [""] + grand, 0, "grand", None, None, "الإجمالي"))
        return {"columns": cols, "lines": lines, "first_col": _("Asset"), "first_col_ar": "الأصل"}

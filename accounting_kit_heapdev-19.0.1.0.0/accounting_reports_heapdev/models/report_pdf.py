# -*- coding: utf-8 -*-
from odoo import api, models


class ReportAccFinancialPdf(models.AbstractModel):
    _name = "report.accounting_reports_heapdev.report_acc_financial_pdf"
    _description = "Accounting Report PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        options = (data or {}).get("options") or {}
        values = self.env["acc.report.engine"].get_pdf_values(options)
        values.update({"doc_ids": docids, "doc_model": "acc.report.engine", "docs": self.env.company})
        return values

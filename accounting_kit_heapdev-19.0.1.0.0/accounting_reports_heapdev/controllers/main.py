# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request

try:
    from odoo.http import content_disposition
except ImportError:  # Odoo 20 moved it to odoo.http.stream
    from odoo.http.stream import content_disposition


class AccReportController(http.Controller):

    @http.route("/accounting_reports_heapdev/xlsx", type="http", auth="user", methods=["GET"])
    def acc_report_xlsx(self, options="{}", **kw):
        opts = json.loads(options or "{}")
        content, filename = request.env["acc.report.engine"].export_xlsx(opts)
        return request.make_response(content, headers=[
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])

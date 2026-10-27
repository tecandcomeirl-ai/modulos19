# -*- coding: utf-8 -*-
{
    "name": "Accounting Reports - Dynamic Financial Reports for Community",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Free dynamic financial reports for Odoo 19 Community: Profit and Loss, Balance Sheet, Cash Flow Statement, General Ledger, Trial Balance, Partner Ledger, Journal Audit, Aged Receivable, Aged Payable and Tax / VAT report (UAE FTA, KSA ZATCA). On-screen report viewer with drill-down to journal items, comparison periods, date, journal, analytic, partner and posted filters, PDF and Excel XLSX export, bilingual English Arabic. Enterprise-like accounting reports, التقارير المالية",
    "description": """
Accounting Reports for Odoo Community (accounting_reports_heapdev)
==================================================================
* Profit and Loss, Balance Sheet, Cash Flow Statement (direct method)
* General Ledger, Trial Balance, Partner Ledger, Journal Audit
* Aged Receivable / Aged Payable with 30-day buckets
* Tax / VAT report with a UAE FTA 201 / KSA ZATCA style summary
* On-screen viewer: fold / unfold, drill down to journal items and entries
* Filters: date presets, custom dates, journals, analytic accounts, partners, posted only
* Comparison with previous periods or the same period last year, variance %
* Bilingual English / Arabic PDF and Excel (XLSX) export
    """,
    "author": "Adil Akbar",
    "website": "https://github.com/aadilakbar",
    "maintainer": "Adil Akbar",
    "support": "adilak389@gmail.com",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "report/acc_report_templates.xml",
        "views/acc_report_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "accounting_reports_heapdev/static/src/scss/acc_report.scss",
            "accounting_reports_heapdev/static/src/js/acc_report_common.js",
            "accounting_reports_heapdev/static/src/js/acc_report_action.js",
            "accounting_reports_heapdev/static/src/xml/acc_report_action.xml",
        ],
    },
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": False,
    "auto_install": False,
}

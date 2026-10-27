# -*- coding: utf-8 -*-
{
    "name": "Accounting Kit - Full Accounting for Odoo 19 Community (Free)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Free complete accounting kit for Odoo 19 Community, Enterprise-like accounting: dynamic financial reports (Profit and Loss, Balance Sheet, Cash Flow, General Ledger, Trial Balance, Partner Ledger, Aged Receivable / Payable, Journal Audit, Tax VAT report UAE KSA), accounting dashboard, asset management and depreciation, deferred revenue and expense, customer follow-up and statements, recurring entries, lock dates, post dated cheques PDC, full accounting menus. Optional paid add-ons: budget vs actual and bank statement import / reconciliation. PDF and Excel, bilingual English Arabic. Free alternative to Odoo Enterprise accounting, المحاسبة الكاملة",
    "description": """
Accounting Kit for Odoo Community (accounting_kit_heapdev)
==========================================================
Installs the complete free accounting suite:

* accounting_reports_heapdev: dynamic financial reports with drill-down, PDF and XLSX
* accounting_asset_heapdev: assets, depreciation, deferred revenue and expenses
* accounting_followup_heapdev: payment follow-up and customer statements
* accounting_tools_heapdev: dashboard, full accounting menus, recurring entries, lock dates, PDC

Optional paid add-ons (USD 34.44 each, OPL-1, not installed by the kit):

* accounting_budget_heapdev: budgets and budget vs actual
* accounting_bank_heapdev: bank statement import and reconciliation
    """,
    "author": "Adil Akbar",
    "website": "https://github.com/aadilakbar",
    "maintainer": "Adil Akbar",
    "support": "adilak389@gmail.com",
    "license": "LGPL-3",
    "depends": [
        "accounting_reports_heapdev",
        "accounting_asset_heapdev",
        "accounting_followup_heapdev",
        "accounting_tools_heapdev",
    ],
    "data": [],
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": True,
    "auto_install": False,
}

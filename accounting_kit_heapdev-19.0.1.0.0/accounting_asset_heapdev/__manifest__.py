# -*- coding: utf-8 -*-
{
    "name": "Asset Management & Deferred Revenue / Expense for Community",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Free fixed asset management for Odoo 19 Community: asset register, asset categories, straight-line (linear) and declining balance (degressive) depreciation, prorata temporis, depreciation board, automatic depreciation journal entries by scheduled action, asset disposal / sale with gain or loss, deferred revenue and deferred (prepaid) expense recognition, assets created from vendor bills, depreciation schedule report. Bilingual English Arabic, إدارة الأصول الثابتة والإهلاك",
    "description": """
Asset Management for Odoo Community (accounting_asset_heapdev)
==============================================================
* Asset categories with journal, accounts, method, duration and period
* Linear and degressive (declining balance) depreciation, prorata temporis, salvage value
* Depreciation board, one click or scheduled (cron) posting of depreciation entries
* Dispose / sell an asset with automatic gain or loss entry
* Deferred revenue and deferred expense recognition with the same engine
* Assets created automatically when a bill or invoice is posted on an asset account
* Depreciation schedule report in the Accounting Reports viewer (PDF / XLSX)
    """,
    "author": "Adil Akbar",
    "website": "https://github.com/aadilakbar",
    "maintainer": "Adil Akbar",
    "support": "adilak389@gmail.com",
    "license": "LGPL-3",
    "depends": ["account", "mail", "accounting_reports_heapdev"],
    "data": [
        "security/ir.model.access.csv",
        "data/acc_asset_data.xml",
        "wizard/acc_asset_dispose_views.xml",
        "views/acc_asset_category_views.xml",
        "views/acc_asset_views.xml",
        "views/account_account_views.xml",
        "views/acc_asset_menus.xml",
    ],
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": False,
    "auto_install": False,
}

# -*- coding: utf-8 -*-
{
    "name": "Accounting Tools - Dashboard, Recurring Entries, Lock Dates, PDC Cheques for Community",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Free accounting tools for Odoo 19 Community: unlock full accounting features and menus (journal items, journal entries, chart of accounts) for the accounting manager, accounting dashboard with KPI cards and charts (revenue, expenses, net profit, cash, receivables, payables, VAT), recurring journal entries with scheduled posting, lock dates screen, post dated cheques (PDC) register for received and issued cheques with register, deposit, clear and bounce entries. Bilingual English Arabic, أدوات المحاسبة والشيكات المؤجلة",
    "description": """
Accounting Tools for Odoo Community (accounting_tools_heapdev)
==============================================================
* Full accounting features and menus for the accounting manager (Invoicing becomes Accounting)
* Accounting dashboard: KPI cards and charts, click through to the reports
* Recurring journal entries: daily, weekly, monthly or yearly, automatic posting by cron
* Lock dates screen for every lock date of your Odoo version
* Post dated cheques register (received / issued): register, deposit, clear and bounce with journal entries
    """,
    "author": "Adil Akbar",
    "website": "https://github.com/aadilakbar",
    "maintainer": "Adil Akbar",
    "support": "adilak389@gmail.com",
    "license": "LGPL-3",
    "depends": ["account", "mail", "accounting_reports_heapdev"],
    "data": [
        "security/ir.model.access.csv",
        "data/acc_tools_data.xml",
        "wizard/acc_lock_date_views.xml",
        "views/acc_recurring_views.xml",
        "views/acc_pdc_views.xml",
        "views/res_company_views.xml",
        "views/acc_tools_menus.xml",
    ],
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": False,
    "auto_install": False,
}

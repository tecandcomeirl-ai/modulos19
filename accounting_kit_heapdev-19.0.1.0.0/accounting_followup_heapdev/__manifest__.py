# -*- coding: utf-8 -*-
{
    "name": "Customer Follow-up & Statements - Payment Reminders for Community",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Free customer payment follow-up for Odoo 19 Community: follow-up levels by days overdue, payment reminder emails and letters, customer account statements with aging (current, 1-30, 31-60, 61-90, 90+), overdue invoices list, next action date, follow-up notes, manual actions as activities, batch follow-up run, credit control and debt collection. Bilingual English Arabic statement PDF, متابعة الذمم المدينة وكشف حساب العميل",
    "description": """
Customer Follow-up for Odoo Community (accounting_followup_heapdev)
===================================================================
* Follow-up levels: days overdue, email, letter and manual action
* Total due, total overdue and current level on every customer
* Payment reminder email (composer opens prefilled) and printable letter
* Customer statement PDF (English / Arabic) with open invoices and aging buckets
* Batch follow-up run, next action date, responsible and notes, activities for manual actions
    """,
    "author": "Adil Akbar",
    "website": "https://github.com/aadilakbar",
    "maintainer": "Adil Akbar",
    "support": "adilak389@gmail.com",
    "license": "LGPL-3",
    "depends": ["account", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/acc_followup_data.xml",
        "report/acc_followup_report.xml",
        "wizard/acc_followup_run_views.xml",
        "views/acc_followup_views.xml",
    ],
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": False,
    "auto_install": False,
}

# -*- coding: utf-8 -*-
{
    "name": "Petty Cash Book",
    "summary": "Track a physical cash box - record cash in / cash out and always "
               "know the balance on hand, with a printable statement.",
    "description": """
Petty Cash Book (Free)
======================
A simple, complete petty-cash tracker for the front desk, a project or a branch.

* **Cash in / cash out** - log every movement with date, description, payee and reference.
* **Live balance** - opening balance plus ins minus outs, always up to date.
* **Printable statement** - a clean PDF of the cash book with a running balance.
* **Multi-book & multi-company** - one book per box, per branch or per person.

Outgrown a single box? **Petty Cash Pro** adds approvals, replenishment, categories
and accounting journal integration.

----

More apps by Arun A George - https://arunalexgeorge.online
""",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "author": "Arun A George",
    "maintainer": "Arun A George",
    "website": "https://arunalexgeorge.online",
    "support": "admin@arunalexgeorge.online",
    "license": "LGPL-3",
    "images": ["static/description/banner.png"],
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "report/petty_cash_report.xml",
        "views/petty_cash_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}

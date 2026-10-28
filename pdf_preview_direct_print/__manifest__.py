# -*- coding: utf-8 -*-
#############################################################################
#
#    MM Solutions
#    Copyright (C) 2026 MM Solutions (https://apps.odoo.com/apps/modules/browse?author=MM%20Solutions)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License v3 (LGPL-3)
#    as published by the Free Software Foundation. See the LICENSE file.
#
#############################################################################
{
    'name': 'Instant Print - Report Preview and One Click Printing',
    'version': '19.0.1.1.6',
    'summary': """Preview any PDF report inside Odoo and print it in one click -
    no more downloading files before printing. Works with invoices, sales orders,
    delivery slips, purchase orders and every custom QWeb PDF report.
    odoo pdf preview | odoo direct print | print without download | report preview odoo |
    pdf viewer odoo backend | one click print odoo | instant print reports odoo |
    preview invoice pdf | preview delivery slip | preview before print odoo |
    odoo report printing | odoo print dialog | odoo 19 direct print""",
    'description': """
Preview and print any QWeb PDF report directly inside Odoo.

By default, Odoo downloads every PDF report to your computer before you can
print it. This module replaces that flow: the report opens instantly in a
preview dialog inside the backend, and a single Print button sends it straight
to your system print dialog. You can still download the file from the same
dialog when you need a copy.

Key features:
- Instant in-app preview of any qweb-pdf report (invoices, SO, PO, delivery
  slips, payslips, custom reports - everything)
- One-click Print button using the browser's native print flow
- Download button kept in the dialog for when you really want the file
- Zero configuration - install and it just works
- Safe fallback: if a report cannot be previewed, Odoo's standard download
  behaviour is used automatically
- No external services, no data leaves your server
    """,
    'author': 'MM Solutions',
    'maintainer': 'MM Solutions',
    'company': 'MM Solutions',
    'website': 'https://apps.odoo.com/apps/modules/browse?author=MM%20Solutions',
    'support': 'SUPPORT_EMAIL_HERE',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'pdf_preview_direct_print/static/src/pdf_preview/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}

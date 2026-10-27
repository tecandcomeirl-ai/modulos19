# -*- coding: utf-8 -*-
##############################################################################
#
#    ERP Artists
#    Copyright (C) 2025-TODAY ERP Artists (<https://www.erpartists.com>).
#    Author: ERP Artists (<https://www.erpartists.com>)
#
##############################################################################
{
    'name': 'WhatsApp Connector',
    'version': '19.0.1.0.0',
    'category': 'Productivity/WhatsApp',
    'summary': 'Send and receive WhatsApp messages from Odoo by scanning a QR code (no Meta API needed)',
    'description': """
WhatsApp Connector
=====================
Connect one or more WhatsApp numbers to Odoo through a lightweight Node.js
gateway (Baileys / WhatsApp Web protocol). Pair a number by scanning a QR code,
then send and receive WhatsApp messages directly from Odoo.

* WhatsApp-style Chats screen: contacts with profile pictures, bubbles, sent / delivered / read ticks, live updates
* Multiple WhatsApp accounts, live QR pairing inside the account form
* Send text, images, videos, audio and documents to contacts
* Send WhatsApp from any contact (and from any document with a partner)
* Incoming messages logged and posted on the contact's chatter
* Delivery / read status tracking
* Unknown senders can automatically become contacts
* Dashboard: KPIs, daily activity chart, delivery funnel, recent messages, top contacts
* Multi-company aware, User / Administrator access levels
    """,
    'author': 'ERP Artists',
    'website': 'https://www.erpartists.com/',
    'license': 'LGPL-3',
    'depends': ['mail', 'phone_validation'],
    'data': [
        'security/ea_whatsapp_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'wizard/ea_whatsapp_composer_views.xml',
        'views/ea_whatsapp_account_views.xml',
        'views/ea_whatsapp_message_views.xml',
        'views/res_partner_views.xml',
        'views/ea_whatsapp_dashboard_views.xml',
        'views/ea_whatsapp_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ea_whatsapp_connector/static/src/**/*',
        ],
        'web.assets_web_dark': [
            'ea_whatsapp_connector/static/dark/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'application': True,
    'installable': True,
    'price': 0.00,
    'currency': 'USD',

}

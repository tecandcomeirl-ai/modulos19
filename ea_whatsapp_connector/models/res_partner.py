# -*- coding: utf-8 -*-
import base64
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    ea_whatsapp_message_ids = fields.One2many('ea.whatsapp.message', 'partner_id', string='WhatsApp Messages')
    ea_whatsapp_message_count = fields.Integer(compute='_compute_ea_whatsapp_message_count')
    ea_whatsapp_avatar_checked = fields.Datetime(copy=False, readonly=True)

    def _ea_whatsapp_set_avatar_from_url(self, url):
        """Use the WhatsApp profile picture as contact image (only when the contact has none)."""
        self.ensure_one()
        self.sudo().ea_whatsapp_avatar_checked = fields.Datetime.now()
        if self.image_1920 or not url:
            return
        try:
            response = requests.get(url, timeout=10)
            if response.ok and response.headers.get('Content-Type', '').startswith('image/'):
                self.sudo().image_1920 = base64.b64encode(response.content)
        except requests.exceptions.RequestException as e:
            _logger.info('WhatsApp avatar download failed for partner %s: %s', self.id, e)

    def _compute_ea_whatsapp_message_count(self):
        data = self.env['ea.whatsapp.message']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.ea_whatsapp_message_count = counts.get(partner.id, 0)

    @api.model
    def _ea_whatsapp_find_partner(self, number, company=None):
        """Find a contact whose phone matches the given international number (digits only)."""
        digits = re.sub(r'\D', '', number or '')
        if len(digits) < 6:
            return self.browse()
        tail = digits[-8:]
        # phone numbers are stored in many formats: search loosely, then compare digits
        pattern = '%' + '%'.join(tail) + '%'
        domain = [('phone', '=like', pattern)]
        if company:
            domain += [('company_id', 'in', [False, company.id])]
        candidates = self.with_context(active_test=True).search(domain, limit=50)
        Message = self.env['ea.whatsapp.message']
        for partner in candidates:
            normalized = Message._normalize_number(partner.phone, partner)
            if normalized and (normalized == digits or normalized.endswith(digits) or digits.endswith(normalized)):
                return partner
        return self.browse()

    def action_ea_whatsapp_messages(self):
        """Open this contact's conversation in the Chats screen."""
        self.ensure_one()
        number = self.env['ea.whatsapp.message']._normalize_number(self.phone, self) if self.phone else False
        last = self.env['ea.whatsapp.message'].search([('partner_id', '=', self.id)], limit=1, order='id desc')
        number = last.number or number
        if not number:
            raise UserError(_('This contact has no phone number.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'ea_whatsapp_chat',
            'name': _('WhatsApp Chats'),
            'context': {'active_number': number},
        }

    def action_ea_whatsapp_send(self):
        partners = self.filtered('phone')
        if not partners:
            raise UserError(_('The selected contact(s) have no phone number.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp'),
            'res_model': 'ea.whatsapp.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'res.partner',
                'active_ids': partners.ids,
                'active_id': partners[:1].id,
            },
        }

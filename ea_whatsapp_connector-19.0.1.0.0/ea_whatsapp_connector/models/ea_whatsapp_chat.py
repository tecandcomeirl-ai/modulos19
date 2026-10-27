# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

AVATAR_RECHECK = timedelta(days=7)


class EaWhatsappMessage(models.Model):
    """Data layer of the WhatsApp-style Chats screen."""
    _inherit = 'ea.whatsapp.message'

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    @api.model
    def _chat_contact(self, number, partner):
        return {
            'number': number,
            'partner_id': partner.id or False,
            'name': partner.display_name if partner else f'+{number}',
            'avatar': f'/web/image/res.partner/{partner.id}/avatar_128' if partner else False,
        }

    def _chat_message_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'direction': self.direction,
            'body': self.body or '',
            'state': self.state,
            'date': fields.Datetime.to_string(self.message_date),
            'error': self.error_message or False,
            'author': self.user_id.name if self.direction == 'out' and self.user_id else False,
            'attachments': [{
                'id': att.id,
                'name': att.name,
                'mimetype': att.mimetype or '',
                'is_image': (att.mimetype or '').startswith('image/'),
                'url': f'/web/content/{att.id}',
                'preview': f'/web/image/{att.id}/400x400',
            } for att in self.attachment_ids],
        }

    # ------------------------------------------------------------------
    # Conversations list
    # ------------------------------------------------------------------
    @api.model
    def chat_get_conversations(self, search=None, account_id=False, limit=100):
        domain = []
        if account_id:
            domain.append(('account_id', '=', int(account_id)))
        search = (search or '').strip()
        if search:
            digits = re.sub(r'\D', '', search)
            term = ['|', ('partner_id.name', 'ilike', search), ('body', 'ilike', search)]
            domain += ['|', ('number', 'ilike', digits)] + term if digits else term

        groups = self._read_group(domain, ['number'], ['id:max'], order='id:max desc', limit=limit)
        last_messages = self.browse([last_id for _number, last_id in groups])
        unread = dict(self._read_group(
            [('number', 'in', [number for number, _id in groups]), ('direction', '=', 'in'),
             ('is_read', '=', False)] + ([('account_id', '=', int(account_id))] if account_id else []),
            ['number'], ['__count']))

        conversations = []
        for message in last_messages:
            partner = message.partner_id or self.search(
                [('number', '=', message.number), ('partner_id', '!=', False)], limit=1).partner_id
            conversations.append({
                **self._chat_contact(message.number, partner),
                'last': message._chat_message_dict(),
                'unread': unread.get(message.number, 0),
            })

        # contacts with a phone but no conversation yet, to start a new chat
        contacts = []
        if search:
            known = {c['partner_id'] for c in conversations if c['partner_id']}
            partners = self.env['res.partner'].search([
                ('phone', '!=', False), ('id', 'not in', list(known)),
                '|', ('name', 'ilike', search), ('phone', 'ilike', search)], limit=10)
            for partner in partners:
                number = self._normalize_number(partner.phone, partner)
                if number:
                    contacts.append(self._chat_contact(number, partner))
            digits = re.sub(r'\D', '', search)
            if len(digits) >= 8 and not any(c['number'] == digits for c in conversations + contacts):
                contacts.append(self._chat_contact(self._normalize_number(search) or digits, self.env['res.partner']))
        return {'conversations': conversations, 'contacts': contacts}

    # ------------------------------------------------------------------
    # One conversation
    # ------------------------------------------------------------------
    @api.model
    def chat_get_messages(self, number, before_id=False, limit=50):
        number = re.sub(r'\D', '', number or '')
        if not number:
            raise UserError(_('Missing phone number.'))
        domain = [('number', '=', number)]
        if before_id:
            domain.append(('id', '<', int(before_id)))
        messages = self.search(domain, order='id desc', limit=limit)

        partner = messages.partner_id[:1] or self.env['res.partner']._ea_whatsapp_find_partner(number)
        self._chat_sync_avatar(number, partner)
        account = messages.account_id[:1] or self.env['ea.whatsapp.account']._get_default_account()

        if not before_id:
            unread = self.search([('number', '=', number), ('direction', '=', 'in'), ('is_read', '=', False)])
            if unread:
                unread.write({'is_read': True})
        return {
            'contact': {
                **self._chat_contact(number, partner),
                'phone': partner.phone if partner else f'+{number}',
            },
            'account': {'id': account.id, 'name': account.name, 'state': account.state} if account else False,
            'messages': [m._chat_message_dict() for m in reversed(messages)],
            'has_more': len(messages) == limit,
        }

    @api.model
    def _chat_sync_avatar(self, number, partner):
        """Fetch the WhatsApp profile picture for contacts without an image (at most weekly)."""
        if not partner or partner.image_1920:
            return
        checked = partner.ea_whatsapp_avatar_checked
        if checked and fields.Datetime.now() - checked < AVATAR_RECHECK:
            return
        account = self.env['ea.whatsapp.account']._get_default_account()
        if not account:
            return
        try:
            url = account.sudo()._gateway_request('GET', f'/avatar/{number}', timeout=10).get('url')
        except UserError:
            url = False
        partner._ea_whatsapp_set_avatar_from_url(url)

    @api.model
    def chat_mark_read(self, number):
        self.search([('number', '=', number), ('direction', '=', 'in'), ('is_read', '=', False)]).write(
            {'is_read': True})
        return True

    @api.model
    def chat_send(self, number, body='', files=None, account_id=False):
        number = re.sub(r'\D', '', number or '')
        body = (body or '').strip()
        files = files or []
        if not number or (not body and not files):
            raise UserError(_('Nothing to send.'))

        last = self.search([('number', '=', number)], limit=1, order='id desc')
        Account = self.env['ea.whatsapp.account']
        account = Account.browse(int(account_id)) if account_id else last.account_id
        if not account or account.state != 'connected':
            account = Account._get_default_account()
        if not account:
            raise UserError(_('No connected WhatsApp account. Connect one in WhatsApp > Configuration > Accounts.'))
        partner = last.partner_id or self.env['res.partner']._ea_whatsapp_find_partner(number, account.company_id)

        message = self.create({
            'account_id': account.id,
            'direction': 'out',
            'number': number,
            'partner_id': partner.id or False,
            'body': body or False,
            'res_model': 'res.partner' if partner else False,
            'res_id': partner.id or False,
        })
        if files:
            attachments = self.env['ir.attachment'].create([{
                'name': f.get('name') or 'file',
                'datas': f.get('data'),
                'mimetype': f.get('mimetype') or 'application/octet-stream',
                'res_model': self._name,
                'res_id': message.id,
            } for f in files])
            message.attachment_ids = [(6, 0, attachments.ids)]
        message._send()
        return message._chat_message_dict()

    def chat_retry(self):
        self.filtered(lambda m: m.direction == 'out' and m.state == 'failed')._send()
        return [m._chat_message_dict() for m in self]

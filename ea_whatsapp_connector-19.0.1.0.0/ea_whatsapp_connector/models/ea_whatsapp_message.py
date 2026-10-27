# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime, timedelta, timezone

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

ACK_ORDER = ['sent', 'delivered', 'read']


class EaWhatsappMessage(models.Model):
    _name = 'ea.whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'message_date desc, id desc'
    _rec_name = 'display_body'

    account_id = fields.Many2one('ea.whatsapp.account', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    direction = fields.Selection([('in', 'Incoming'), ('out', 'Outgoing')], required=True, default='out')
    state = fields.Selection([
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('failed', 'Failed'),
    ], default='queued', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Contact', index=True, ondelete='set null')
    number = fields.Char(string='WhatsApp Number', required=True,
                         help='International number without "+", e.g. 919876543210')
    body = fields.Text()
    display_body = fields.Char(compute='_compute_display_body')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    wa_message_id = fields.Char(string='WhatsApp Message ID', index=True, copy=False, readonly=True)
    error_message = fields.Text(readonly=True, copy=False)
    message_date = fields.Datetime(default=fields.Datetime.now, required=True)
    user_id = fields.Many2one('res.users', string='Sent By', default=lambda self: self.env.user)
    res_model = fields.Char(string='Related Model', index=True)
    res_id = fields.Many2oneReference(string='Related Record', model_field='res_model')
    is_read = fields.Boolean(default=True, index=True, help='Incoming message seen in the Chats screen.')

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        messages._notify_chat_update()
        return messages

    def write(self, vals):
        res = super().write(vals)
        if {'state', 'body', 'partner_id'} & set(vals):
            self._notify_chat_update()
        return res

    def _notify_chat_update(self):
        """Tell open Chats screens (all WhatsApp users) that these conversations changed."""
        group = self.env.ref('ea_whatsapp_connector.group_ea_whatsapp_user', raise_if_not_found=False)
        if group and self:
            group.sudo()._bus_send('ea_whatsapp/chat_update', {'numbers': list(set(self.mapped('number')))})

    @api.depends('body', 'attachment_ids')
    def _compute_display_body(self):
        for message in self:
            text = (message.body or '').strip().splitlines()
            label = text[0] if text else ', '.join(message.attachment_ids.mapped('name'))
            message.display_body = (label or _('(empty)'))[:80]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _normalize_number(self, number, partner=None):
        """Return an international number made of digits only, or False."""
        if not number:
            return False
        country = (partner and partner.country_id) or self.env.company.country_id
        formatted = self.env['res.partner']._phone_format(number=number, country=country, force_format='E164')
        digits = re.sub(r'\D', '', formatted or number)
        return digits or False

    def _related_record(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            record = self.env[self.res_model].browse(self.res_id).exists()
            if record and hasattr(record, 'message_post'):
                return record
        return None

    # ------------------------------------------------------------------
    # Outgoing
    # ------------------------------------------------------------------
    def _send(self, raise_exception=False):
        for message in self.filtered(lambda m: m.direction == 'out' and m.state in ('queued', 'failed')):
            try:
                attachments = message.attachment_ids
                wa_id = message.account_id._send_payload(
                    message.number, message.body, attachments[:1] if attachments else None)
                # WhatsApp takes one media per message: send extra attachments separately
                for attachment in attachments[1:]:
                    message.account_id._send_payload(message.number, None, attachment)
                message.write({'state': 'sent', 'wa_message_id': wa_id, 'error_message': False,
                               'message_date': fields.Datetime.now()})
            except UserError as e:
                message.write({'state': 'failed', 'error_message': str(e)})
                if raise_exception:
                    raise
        return True

    def action_send(self):
        self._send(raise_exception=len(self) == 1)
        return True

    def action_open_related(self):
        self.ensure_one()
        record = self._related_record()
        if not record:
            raise UserError(_('The related document no longer exists.'))
        return {'type': 'ir.actions.act_window', 'res_model': record._name,
                'res_id': record.id, 'view_mode': 'form'}

    # ------------------------------------------------------------------
    # Incoming (called from the webhook, in sudo)
    # ------------------------------------------------------------------
    @api.model
    def _process_inbound(self, account, data):
        wa_id = data.get('id')
        if wa_id and self.search_count([('account_id', '=', account.id), ('wa_message_id', '=', wa_id)]):
            return self.browse()  # duplicate delivery
        number = re.sub(r'\D', '', data.get('from') or '')
        if not number:
            return self.browse()

        partner = self.env['res.partner']._ea_whatsapp_find_partner(number, account.company_id)
        if not partner and account.auto_create_partner:
            partner = self.env['res.partner'].create({
                'name': data.get('push_name') or f'+{number}',
                'phone': f'+{number}',
            })

        timestamp = data.get('timestamp')
        message_date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).replace(tzinfo=None) if timestamp else fields.Datetime.now()
        message = self.create({
            'account_id': account.id,
            'direction': 'in',
            'state': 'received',
            'number': number,
            'partner_id': partner.id if partner else False,
            'body': data.get('text') or False,
            'wa_message_id': wa_id,
            'message_date': message_date,
            'user_id': False,
            'is_read': False,
        })
        if partner and data.get('avatar_url') and not partner.image_1920:
            partner._ea_whatsapp_set_avatar_from_url(data['avatar_url'])

        media = data.get('media')
        if media and media.get('data'):
            raw = account._decode_media(media)
            if raw:
                attachment = self.env['ir.attachment'].create({
                    'name': media.get('filename') or 'whatsapp_media',
                    'raw': raw,
                    'mimetype': media.get('mimetype'),
                    'res_model': self._name,
                    'res_id': message.id,
                })
                message.attachment_ids = [(4, attachment.id)]

        message._post_inbound_on_chatter()
        return message

    def _post_inbound_on_chatter(self):
        self.ensure_one()
        body = Markup('<p><b>%s</b></p><p>%s</p>') % (
            _('WhatsApp message received'),
            Markup('<br/>').join(html_escape(line) for line in (self.body or '').splitlines()),
        )
        targets = []
        if self.partner_id:
            targets.append(self.partner_id)
        if self.account_id.post_on_related_document and self.partner_id:
            last_out = self.search([
                ('account_id', '=', self.account_id.id),
                ('partner_id', '=', self.partner_id.id),
                ('direction', '=', 'out'),
                ('res_model', '!=', False),
                ('res_model', '!=', 'res.partner'),
                ('message_date', '>=', fields.Datetime.now() - timedelta(days=7)),
            ], limit=1)
            record = last_out._related_record() if last_out else None
            if record:
                targets.append(record)
                self.write({'res_model': record._name, 'res_id': record.id})
        for record in targets:
            attachments = self.attachment_ids.copy({'res_model': record._name, 'res_id': record.id}) \
                if self.attachment_ids else self.env['ir.attachment']
            record.message_post(
                body=body,
                author_id=self.partner_id.id or False,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                attachment_ids=attachments.ids,
            )

    @api.model
    def _process_ack(self, account, data):
        status = data.get('status')
        if status not in ACK_ORDER or not data.get('id'):
            return
        message = self.search([('account_id', '=', account.id), ('wa_message_id', '=', data['id']),
                               ('direction', '=', 'out')], limit=1)
        # never move a status backwards (acks can arrive out of order)
        if message and message.state in ACK_ORDER and ACK_ORDER.index(status) > ACK_ORDER.index(message.state):
            message.state = status

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, days=7, account_id=False):
        days = max(1, min(int(days or 7), 365))
        today = fields.Date.context_today(self)
        start_date = today - timedelta(days=days - 1)
        start = fields.Datetime.to_datetime(start_date)
        domain = [('message_date', '>=', start)]
        if account_id:
            domain.append(('account_id', '=', int(account_id)))

        counts = {(direction, state): count for direction, state, count in self._read_group(
            domain, ['direction', 'state'], ['__count'])}
        out = lambda *states: sum(counts.get(('out', s), 0) for s in states)
        sent = out('sent', 'delivered', 'read')
        delivered = out('delivered', 'read')
        read = out('read')
        failed = out('failed')
        received = counts.get(('in', 'received'), 0)
        contacts = len(self._read_group(domain + [('partner_id', '!=', False)], ['partner_id']))

        per_day = {(day.date() if hasattr(day, 'date') else day, direction): count
                   for day, direction, count in self._read_group(
                       domain, ['message_date:day', 'direction'], ['__count'])}
        dates = [start_date + timedelta(days=i) for i in range(days)]

        top = self._read_group(domain + [('partner_id', '!=', False)], ['partner_id'], ['__count'],
                               order='__count desc', limit=5)
        recent = self.search(domain, limit=8)
        accounts = self.env['ea.whatsapp.account'].search([])
        pct = lambda part, whole: round(100.0 * part / whole, 1) if whole else 0.0

        return {
            'start': fields.Datetime.to_string(start),
            'kpis': {
                'sent': sent, 'delivered': delivered, 'read': read, 'failed': failed,
                'received': received, 'contacts': contacts,
                'delivery_rate': pct(delivered, sent), 'read_rate': pct(read, sent),
                'failure_rate': pct(failed, sent + failed),
            },
            'daily': {
                'labels': [fields.Date.to_string(d) for d in dates],
                'outgoing': [per_day.get((d, 'out'), 0) for d in dates],
                'incoming': [per_day.get((d, 'in'), 0) for d in dates],
            },
            'top_contacts': [{'id': p.id, 'name': p.display_name, 'count': c} for p, c in top],
            'recent': [{
                'id': m.id,
                'date': fields.Datetime.to_string(m.message_date),
                'direction': m.direction,
                'contact': m.partner_id.display_name or f'+{m.number}',
                'body': m.display_body,
                'state': m.state,
                'state_label': dict(self._fields['state']._description_selection(self.env))[m.state],
            } for m in recent],
            'accounts': [{
                'id': a.id, 'name': a.name, 'phone': a.phone_number or '',
                'state': a.state,
                'state_label': dict(a._fields['state']._description_selection(self.env))[a.state],
            } for a in accounts],
        }

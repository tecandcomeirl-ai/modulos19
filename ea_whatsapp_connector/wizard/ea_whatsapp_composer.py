# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape


class EaWhatsappComposer(models.TransientModel):
    _name = 'ea.whatsapp.composer'
    _description = 'Send WhatsApp Message'

    account_id = fields.Many2one(
        'ea.whatsapp.account', string='From', required=True,
        domain="[('state', '=', 'connected')]",
        default=lambda self: self.env['ea.whatsapp.account']._get_default_account())
    partner_ids = fields.Many2many('res.partner', string='Recipients')
    number = fields.Char(string='Or Number', help='Send to a number that is not a contact, e.g. +91 98765 43210')
    body = fields.Text(string='Message')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    res_model = fields.Char()
    res_id = fields.Integer()
    missing_phone_ids = fields.Many2many('res.partner', compute='_compute_missing_phone_ids')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('default_partner_ids'):
            return res  # recipients given explicitly (see _action_open_for_record)
        model = self.env.context.get('active_model')
        ids = self.env.context.get('active_ids') or (
            [self.env.context['active_id']] if self.env.context.get('active_id') else [])
        if not model or not ids or model not in self.env:
            return res
        records = self.env[model].browse(ids).exists()
        if model == 'res.partner':
            partners = records
        elif 'partner_id' in records._fields:
            partners = records.mapped('partner_id')
        else:
            partners = self.env['res.partner']
        res['partner_ids'] = [(6, 0, partners.ids)]
        if len(records) == 1:
            res.update(res_model=model, res_id=records.id)
        return res

    @api.model
    def _action_open_for_record(self, record, partner, body, attachments=None, context=None):
        """Open the composer prefilled for a business document (used by the Sales / Invoicing bridges)."""
        if not partner.phone and partner.commercial_partner_id.phone:
            partner = partner.commercial_partner_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp'),
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_ids': [(6, 0, partner.ids)],
                'default_body': body,
                'default_attachment_ids': [(6, 0, attachments.ids if attachments else [])],
                'default_res_model': record._name,
                'default_res_id': record.id,
                **(context or {}),
            },
        }

    @api.model
    def _make_pdf_attachment(self, report_ref, record, filename):
        pdf, _report_type = self.env['ir.actions.report']._render_qweb_pdf(report_ref, record.ids)
        return self.env['ir.attachment'].create({
            'name': filename.replace('/', '_') + '.pdf',
            'raw': pdf,
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': 0,
        })

    @api.depends('partner_ids')
    def _compute_missing_phone_ids(self):
        for wizard in self:
            wizard.missing_phone_ids = wizard.partner_ids.filtered(lambda p: not p.phone)

    def action_send(self):
        self.ensure_one()
        if not self.body and not self.attachment_ids:
            raise UserError(_('Write a message or add an attachment.'))
        Message = self.env['ea.whatsapp.message']
        vals_list = []
        for partner in self.partner_ids.filtered('phone'):
            number = Message._normalize_number(partner.phone, partner)
            if number:
                vals_list.append({'partner_id': partner.id, 'number': number})
        if self.number:
            number = Message._normalize_number(self.number)
            if not number:
                raise UserError(_('"%s" is not a valid phone number.', self.number))
            partner = self.env['res.partner']._ea_whatsapp_find_partner(number, self.account_id.company_id)
            vals_list.append({'partner_id': partner.id or False, 'number': number})
        if not vals_list:
            raise UserError(_('No recipient with a valid phone number.'))

        # keep attachments private to the messages, not to the transient wizard
        self.attachment_ids.write({'res_model': 'ea.whatsapp.message', 'res_id': 0})
        messages = Message.create([{
            **vals,
            'account_id': self.account_id.id,
            'direction': 'out',
            'body': self.body,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)],
            'res_model': self.res_model or 'res.partner',
            'res_id': self.res_id or vals['partner_id'],
        } for vals in vals_list])
        self.attachment_ids.write({'res_id': messages[:1].id})
        messages._send(raise_exception=len(messages) == 1)
        self._log_on_related_document(messages)

        failed = messages.filtered(lambda m: m.state == 'failed')
        if failed:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'type': 'warning', 'sticky': True,
                    'message': _('%(ok)s message(s) sent, %(ko)s failed. See WhatsApp > Messages.',
                                 ok=len(messages) - len(failed), ko=len(failed)),
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        return {'type': 'ir.actions.act_window_close'}

    def _log_on_related_document(self, messages):
        sent = messages.filtered(lambda m: m.state == 'sent')
        if not sent:
            return
        text = Markup('<br/>').join(html_escape(line) for line in (self.body or '').splitlines())
        if self.res_model and self.res_model != 'res.partner' and self.res_id:
            record = self.env[self.res_model].browse(self.res_id).exists()
            if record and hasattr(record, 'message_post'):
                names = ', '.join(sent.mapped(lambda m: m.partner_id.name or f'+{m.number}'))
                record.message_post(
                    body=Markup('<p><b>%s</b></p><p>%s</p>') % (_('WhatsApp sent to %s', names), text),
                    message_type='comment', subtype_xmlid='mail.mt_note',
                    attachment_ids=self._chatter_attachment_ids())
            return
        for message in sent.filtered('partner_id'):
            message.partner_id.message_post(
                body=Markup('<p><b>%s</b></p><p>%s</p>') % (_('WhatsApp message sent'), text),
                message_type='comment', subtype_xmlid='mail.mt_note',
                attachment_ids=self._chatter_attachment_ids())

    def _chatter_attachment_ids(self):
        # copies owned by the composer model are re-attached to the record by message_post
        return [attachment.copy({'res_model': 'mail.compose.message', 'res_id': 0}).id
                for attachment in self.attachment_ids]

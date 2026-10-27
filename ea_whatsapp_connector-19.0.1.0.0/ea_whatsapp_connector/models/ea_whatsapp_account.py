# -*- coding: utf-8 -*-
import base64
import logging
import secrets
import uuid

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Gateway status -> account state
GATEWAY_STATE_MAP = {
    'starting': 'connecting',
    'connecting': 'connecting',
    'qr': 'qr',
    'connected': 'connected',
    'disconnected': 'disconnected',
    'logged_out': 'disconnected',
    'not_found': 'disconnected',
}


class EaWhatsappAccount(models.Model):
    _name = 'ea.whatsapp.account'
    _description = 'WhatsApp Account'
    _inherit = ['mail.thread']
    _order = 'is_default desc, sequence, id'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(
        string='Default Account',
        help='Used when sending a message without choosing an account explicitly.')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    # Gateway connection
    gateway_url = fields.Char(
        string='Gateway URL', required=True, default='http://localhost:3000',
        help='Base URL of the EA WhatsApp gateway (Node.js service shipped in the sidecar folder).')
    api_key = fields.Char(
        string='Gateway API Key', groups='ea_whatsapp_connector.group_ea_whatsapp_manager',
        help='Must match API_KEY configured on the gateway.')
    session_id = fields.Char(
        string='Session ID', required=True, copy=False, readonly=True,
        default=lambda self: uuid.uuid4().hex[:16],
        help='Identifier of this WhatsApp session on the gateway.')
    webhook_token = fields.Char(
        copy=False, readonly=True, default=lambda self: secrets.token_urlsafe(24),
        groups='ea_whatsapp_connector.group_ea_whatsapp_manager')
    callback_base_url = fields.Char(
        string='Odoo URL for Gateway',
        help='URL the gateway uses to reach Odoo (e.g. http://odoo:8069 inside Docker). '
             'Leave empty to use the web.base.url system parameter.')
    webhook_url = fields.Char(compute='_compute_webhook_url')

    # Session status
    state = fields.Selection([
        ('draft', 'Not Connected'),
        ('connecting', 'Connecting'),
        ('qr', 'Waiting for QR Scan'),
        ('connected', 'Connected'),
        ('disconnected', 'Disconnected'),
    ], default='draft', required=True, readonly=True, copy=False, tracking=True)
    qr_code = fields.Binary(string='QR Code', readonly=True, copy=False, attachment=False)
    phone_number = fields.Char(readonly=True, copy=False)
    wa_name = fields.Char(string='WhatsApp Name', readonly=True, copy=False)
    last_sync = fields.Datetime(readonly=True, copy=False)

    # Behaviour
    auto_create_partner = fields.Boolean(
        string='Create Contacts for Unknown Senders', default=True)
    post_on_related_document = fields.Boolean(
        string='Post Replies on Related Document', default=True,
        help='When a contact replies, also post the reply on the document the last '
             'WhatsApp message to this contact was sent from.')

    whatsapp_message_ids = fields.One2many('ea.whatsapp.message', 'account_id', string='WhatsApp Messages')
    message_count = fields.Integer(compute='_compute_message_count')

    _session_uniq = models.Constraint('unique(session_id)', 'The session ID must be unique.')

    @api.depends('callback_base_url')
    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for account in self:
            root = (account.callback_base_url or base or '').rstrip('/')
            token = account.sudo().webhook_token
            account.webhook_url = f'{root}/ea_whatsapp/webhook/{token}' if token else False

    def _compute_message_count(self):
        data = self.env['ea.whatsapp.message']._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count'])
        counts = {account.id: count for account, count in data}
        for account in self:
            account.message_count = counts.get(account.id, 0)

    @api.constrains('is_default', 'company_id')
    def _check_single_default(self):
        for account in self.filtered('is_default'):
            others = self.search_count([
                ('id', '!=', account.id), ('is_default', '=', True),
                ('company_id', '=', account.company_id.id)])
            if others:
                raise ValidationError(_('Only one default WhatsApp account is allowed per company.'))

    @api.model
    def _get_default_account(self, company=None):
        company = company or self.env.company
        domain = [('company_id', '=', company.id), ('state', '=', 'connected')]
        return self.search(domain + [('is_default', '=', True)], limit=1) or self.search(domain, limit=1)

    # ------------------------------------------------------------------
    # Gateway communication
    # ------------------------------------------------------------------
    def _gateway_request(self, method, path, payload=None, timeout=20):
        self.ensure_one()
        url = f"{self.gateway_url.rstrip('/')}/sessions/{self.session_id}{path}"
        headers = {'X-Api-Key': self.sudo().api_key or ''}
        try:
            response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            raise UserError(_('Cannot reach the WhatsApp gateway at %(url)s.\n%(error)s',
                              url=self.gateway_url, error=e)) from e
        try:
            result = response.json()
        except ValueError:
            result = {}
        if response.status_code == 401:
            raise UserError(_('The WhatsApp gateway rejected the API key.'))
        if response.status_code >= 400:
            raise UserError(_('WhatsApp gateway error (%(code)s): %(error)s',
                              code=response.status_code,
                              error=result.get('error') or response.text[:300]))
        return result

    def _apply_gateway_status(self, data):
        """Write a status payload coming from the gateway (poll or webhook)."""
        self.ensure_one()
        status = data.get('status') or 'disconnected'
        vals = {'state': GATEWAY_STATE_MAP.get(status, 'disconnected'), 'last_sync': fields.Datetime.now()}
        qr = data.get('qr')
        if status == 'qr' and qr:
            vals['qr_code'] = qr.split(',', 1)[1] if qr.startswith('data:') else qr
        elif status != 'qr':
            vals['qr_code'] = False
        if status == 'connected':
            if data.get('phone'):
                vals['phone_number'] = data['phone']
            if data.get('name'):
                vals['wa_name'] = data['name']
        if status == 'logged_out':
            vals.update(phone_number=False, wa_name=False)
        # only write changed values to avoid noise in the chatter / DB
        changed = {k: v for k, v in vals.items() if k == 'last_sync' or self[k] != v}
        if 'qr_code' in changed and isinstance(changed['qr_code'], str) and self.qr_code:
            current = self.qr_code.decode() if isinstance(self.qr_code, bytes) else self.qr_code
            if current == changed['qr_code']:
                changed.pop('qr_code')
        self.sudo().write(changed)

    def _sync_status(self, raise_exception=False):
        for account in self:
            try:
                account._apply_gateway_status(account._gateway_request('GET', ''))
            except UserError as e:
                if raise_exception:
                    raise
                _logger.warning('WhatsApp account %s: status sync failed: %s', account.name, e)
                account.sudo().write({'state': 'disconnected', 'qr_code': False})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_connect(self):
        for account in self:
            if not account.webhook_url or account.webhook_url.startswith('/'):
                raise UserError(_('Set the "web.base.url" system parameter or the '
                                  '"Odoo URL for Gateway" field first.'))
            result = account._gateway_request('POST', '/start', {
                'webhook_url': account.webhook_url,
                'webhook_token': account.sudo().webhook_token,
            })
            account._apply_gateway_status(result)
        return True

    def action_refresh_status(self):
        self._sync_status(raise_exception=True)
        return True

    def action_logout(self):
        for account in self:
            account._gateway_request('POST', '/logout')
            account._apply_gateway_status({'status': 'logged_out'})
            account.message_post(body=_('WhatsApp session logged out.'))
        return True

    def action_regenerate_token(self):
        for account in self:
            account.sudo().webhook_token = secrets.token_urlsafe(24)
        return True

    def action_view_messages(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'ea_whatsapp_connector.action_ea_whatsapp_message')
        action['domain'] = [('account_id', '=', self.id)]
        action['context'] = {'default_account_id': self.id}
        return action

    def get_qr_state(self):
        """Called by the QR widget while the form is open."""
        self.ensure_one()
        self._sync_status()
        qr = self.qr_code
        if isinstance(qr, bytes):
            qr = qr.decode()
        return {'state': self.state, 'qr': qr or False, 'phone': self.phone_number or False}

    @api.model
    def _cron_sync_status(self):
        self.search([('state', '!=', 'draft')])._sync_status()

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _send_payload(self, to, text=None, attachment=None):
        """Send a single WhatsApp message. Returns the gateway message id."""
        self.ensure_one()
        if self.state != 'connected':
            raise UserError(_('WhatsApp account "%s" is not connected.', self.name))
        payload = {'to': to, 'text': text or ''}
        if attachment:
            payload['media'] = {
                'data': attachment.datas.decode() if isinstance(attachment.datas, bytes) else attachment.datas,
                'mimetype': attachment.mimetype or 'application/octet-stream',
                'filename': attachment.name,
            }
        result = self._gateway_request('POST', '/messages', payload, timeout=60)
        return result.get('id')

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------
    def _handle_webhook(self, payload):
        self.ensure_one()
        event = payload.get('event')
        data = payload.get('data') or {}
        if event == 'status':
            self._apply_gateway_status(data)
        elif event == 'message':
            self.env['ea.whatsapp.message'].sudo()._process_inbound(self, data)
        elif event == 'ack':
            self.env['ea.whatsapp.message'].sudo()._process_ack(self, data)
        else:
            _logger.debug('WhatsApp webhook: ignoring event %s', event)

    @staticmethod
    def _decode_media(media):
        try:
            return base64.b64decode(media.get('data') or '')
        except (ValueError, TypeError):
            return b''

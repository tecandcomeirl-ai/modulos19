# -*- coding: utf-8 -*-
import hmac
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class EaWhatsappController(http.Controller):

    @http.route('/ea_whatsapp/webhook/<string:token>', type='http', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def webhook(self, token, **kwargs):
        account = request.env['ea.whatsapp.account'].sudo().search(
            [('webhook_token', '=', token)], limit=1)
        header_token = request.httprequest.headers.get('X-Webhook-Token', '')
        if not account or not hmac.compare_digest(header_token, token):
            return request.make_json_response({'error': 'unauthorized'}, status=401)
        try:
            payload = request.get_json_data()
        except ValueError:
            return request.make_json_response({'error': 'invalid json'}, status=400)
        if payload.get('session') and payload['session'] != account.session_id:
            return request.make_json_response({'error': 'session mismatch'}, status=400)
        try:
            account._handle_webhook(payload)
        except Exception:
            _logger.exception('WhatsApp webhook processing failed for account %s', account.id)
            return request.make_json_response({'error': 'processing failed'}, status=500)
        return request.make_json_response({'ok': True})

    @http.route('/ea_whatsapp/account/qr_state', type='jsonrpc', auth='user')
    def qr_state(self, account_id):
        account = request.env['ea.whatsapp.account'].browse(int(account_id)).exists()
        if not account:
            return {'state': 'draft', 'qr': False}
        account.check_access('read')
        return account.get_qr_state()

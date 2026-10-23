import logging
from datetime import timedelta
from urllib.parse import quote_plus

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_pe_sunat_beta.services.ubl_builder import amount_in_words, partner_doc_code

_logger = logging.getLogger(__name__)
DOC_TITLES = {"01": "FACTURA ELECTRÓNICA", "03": "BOLETA DE VENTA ELECTRÓNICA",
              "07": "NOTA DE CRÉDITO ELECTRÓNICA", "08": "NOTA DE DÉBITO ELECTRÓNICA",
              "NV": "NOTA DE VENTA"}


class AccountMove(models.Model):
    _inherit = "account.move"

    sunat_voided = fields.Boolean(string="Dado de baja en SUNAT", readonly=True, copy=False)
    sunat_attempts = fields.Integer(string="Intentos fallidos", compute="_compute_sunat_attempts")
    sunat_number = fields.Char(string="Número SUNAT", compute="_compute_sunat_print")
    sunat_doc_title = fields.Char(compute="_compute_sunat_print")
    sunat_legend = fields.Char(compute="_compute_sunat_print")
    sunat_qr_url = fields.Char(compute="_compute_sunat_print")
    sunat_hash = fields.Char(compute="_compute_sunat_print")

    @api.depends("sunat_document_ids.state")
    def _compute_sunat_attempts(self):
        for move in self:
            move.sunat_attempts = len(move.sunat_document_ids.filtered(lambda d: d.state == "error"))

    @api.depends("name", "amount_total", "amount_tax", "invoice_date", "sunat_doc_type",
                 "sunat_nv_number", "partner_id.vat", "sunat_document_ids.xml_file")
    def _compute_sunat_print(self):
        for move in self:
            move.sunat_doc_title = DOC_TITLES.get(move.sunat_doc_type, "COMPROBANTE")
            number = ""
            qr = ""
            if move.sunat_doc_type == "NV":
                number = move.sunat_nv_number or ""
            elif move.sunat_doc_type:
                try:
                    series, num = move._sunat_series_number()
                    number = "%s-%s" % (series, num)
                    qr = "|".join([
                        move.company_id.vat or "", move.sunat_doc_type, series, num,
                        "%.2f" % move.amount_tax, "%.2f" % move.amount_total,
                        move.invoice_date.isoformat() if move.invoice_date else "",
                        partner_doc_code(move.partner_id) if move.partner_id.vat else "0",
                        move.partner_id.vat or "-", ""])
                except UserError:
                    number = move.name or ""
            move.sunat_number = number
            product_lines = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
            if product_lines and all(getattr(l, "sunat_free_afect", False) for l in product_lines):
                move.sunat_legend = "TRANSFERENCIA GRATUITA DE UN BIEN Y/O SERVICIO PRESTADO GRATUITAMENTE"
            else:
                move.sunat_legend = amount_in_words(move.amount_total, move.currency_id.name) \
                    if move.currency_id else ""
            move.sunat_qr_url = ("/report/barcode/?barcode_type=QR&value=%s&width=140&height=140"
                                 % quote_plus(qr)) if qr else ""
            doc = move.sunat_document_ids.filtered(lambda d: d.digest_value)[:1]
            move.sunat_hash = doc.digest_value if doc else ""

    # ------------------------------------------------------------------ envío
    def _edi_is_sendable(self):
        self.ensure_one()
        if self.move_type not in ("out_invoice", "out_refund") or self.state != "posted":
            return False
        if self.sunat_doc_type in (False, "NV") or self.sunat_voided:
            return False
        if self.sunat_document_ids.filtered(lambda d: d.state in ("accepted", "rejected")):
            return False
        if self.sunat_doc_type == "03" and self.company_id.sunat_boleta_mode == "summary":
            return False  # lo cubre el resumen diario
        return self.sunat_attempts < (self.company_id.sunat_max_attempts or 5)

    def _edi_try_send(self):
        """Envía sin interrumpir el flujo contable si algo falla."""
        for move in self:
            try:
                move.action_send_sunat()
            except UserError as e:
                move.message_post(body=_("Envío SUNAT no realizado: %s", e.args[0]))
            except Exception:  # noqa: BLE001
                _logger.exception("EDI: error enviando %s", move.name)

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.company_id.sunat_auto_send == "post" and move._edi_is_sendable():
                move._edi_try_send()
        return res

    def action_send_sunat(self):
        """Boletas en modo resumen van por RC; el resto por sendBill."""
        boletas = self.filtered(lambda m: m.sunat_doc_type == "03"
                                and m.company_id.sunat_boleta_mode == "summary")
        others = self - boletas
        if boletas:
            for move in boletas:
                move._sunat_check_before_send()
            self.env["sunat.summary"]._send_for_moves(boletas)
        if others:
            return super(AccountMove, others).action_send_sunat()
        return True

    def action_send_sunat_bulk(self):
        """Acción masiva desde la lista: omite los que no aplican."""
        self.filtered(lambda m: m._edi_is_sendable()).action_send_sunat()
        return True

    @api.model
    def _cron_edi_send_pending(self):
        today = fields.Date.context_today(self)
        for company in self.env["res.company"].search([("sunat_auto_send", "in", ("post", "cron"))]):
            moves = self.search([
                ("company_id", "=", company.id), ("state", "=", "posted"),
                ("move_type", "in", ("out_invoice", "out_refund")),
                ("sunat_doc_type", "in", ("01", "03", "07", "08")),
                ("invoice_date", ">=", today - timedelta(days=7))], limit=200)
            moves.filtered(lambda m: m._edi_is_sendable())._edi_try_send()

    # ------------------------------------------------------------------ baja
    def action_void_sunat(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Dar de baja en SUNAT"),
            "res_model": "sunat.void.wizard", "view_mode": "form", "target": "new",
            "context": {"default_move_id": self.id},
        }

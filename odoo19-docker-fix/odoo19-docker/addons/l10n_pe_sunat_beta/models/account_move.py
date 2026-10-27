import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

NUM_RE = re.compile(r"([A-Z0-9]{4})-(\d{1,8})\s*$")

SUNAT_DOC_TYPES = [
    ("01", "Factura"),
    ("03", "Boleta de venta"),
    ("07", "Nota de crédito"),
    ("08", "Nota de débito"),
    ("NV", "Nota de venta (interna)"),
]
# Catálogo 09 - motivos de nota de crédito
CREDIT_REASONS = [
    ("01", "01 - Anulación de la operación"),
    ("02", "02 - Anulación por error en el RUC"),
    ("03", "03 - Corrección por error en la descripción"),
    ("04", "04 - Descuento global"),
    ("05", "05 - Descuento por ítem"),
    ("06", "06 - Devolución total"),
    ("07", "07 - Devolución por ítem"),
    ("08", "08 - Bonificación"),
    ("09", "09 - Disminución en el valor"),
    ("13", "13 - Ajustes de operaciones de exportación / montos y/o fechas de pago"),
]
# Catálogo 10 - motivos de nota de débito
DEBIT_REASONS = [
    ("01", "01 - Intereses por mora"),
    ("02", "02 - Aumento en el valor"),
    ("03", "03 - Penalidades / otros conceptos"),
]


class AccountMove(models.Model):
    _inherit = "account.move"

    sunat_doc_type = fields.Selection(SUNAT_DOC_TYPES, string="Comprobante SUNAT", copy=False)
    sunat_credit_reason = fields.Selection(CREDIT_REASONS, string="Motivo NC (Cat. 09)",
                                           default="01", copy=False)
    sunat_debit_reason = fields.Selection(DEBIT_REASONS, string="Motivo ND (Cat. 10)",
                                          default="02", copy=False)
    sunat_note_description = fields.Char(string="Sustento de la nota", copy=False)
    sunat_nv_number = fields.Char(string="N.º Nota de venta", copy=False, readonly=True)
    sunat_document_ids = fields.One2many("sunat.document", "move_id", string="Envíos SUNAT")
    sunat_state = fields.Selection(
        [("draft", "Borrador"), ("signed", "Firmado"), ("accepted", "Aceptado"),
         ("rejected", "Rechazado"), ("error", "Error")],
        string="Estado SUNAT", compute="_compute_sunat_state")

    # ------------------------------------------------------------------
    @api.depends("sunat_document_ids.state")
    def _compute_sunat_state(self):
        for move in self:
            move.sunat_state = move.sunat_document_ids[:1].state if move.sunat_document_ids else False

    @api.model
    def _sunat_guess_doc_type(self, vals):
        mtype = vals.get("move_type")
        latam_id = vals.get("l10n_latam_document_type_id")
        if latam_id and "l10n_latam_document_type_id" in self._fields:
            code = self.env["l10n_latam.document.type"].browse(latam_id).code
            if code in ("01", "03", "07", "08"):
                return code
        if mtype == "out_refund":
            return "07"
        if vals.get("debit_origin_id"):
            return "08"
        partner = self.env["res.partner"].browse(vals["partner_id"]) if vals.get("partner_id") else None
        if partner and len((partner.vat or "").strip()) != 11:
            return "03"
        return "01"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("sunat_doc_type") and vals.get("move_type") in ("out_invoice", "out_refund"):
                vals["sunat_doc_type"] = self._sunat_guess_doc_type(vals)
        return super().create(vals_list)

    @api.onchange("partner_id")
    def _onchange_partner_sunat_doc_type(self):
        for move in self:
            if move.move_type == "out_invoice" and move.sunat_doc_type in (False, "01", "03") \
                    and not move.debit_origin_id:
                move.sunat_doc_type = "01" if len((move.partner_id.vat or "").strip()) == 11 else "03"

    def action_post(self):
        res = super().action_post()
        for move in self.filtered(lambda m: m.sunat_doc_type == "NV" and not m.sunat_nv_number):
            move.sunat_nv_number = self.env["ir.sequence"].next_by_code("sunat.nota.venta")
        return res

    # ------------------------------------------------------------------
    def _sunat_series_number(self):
        """(serie, correlativo de 8 dígitos) a partir del nombre del asiento."""
        self.ensure_one()
        texts = []
        if "l10n_latam_document_number" in self._fields:
            texts.append(self.l10n_latam_document_number or "")
        texts.append(self.name or "")
        for text in texts:
            match = NUM_RE.search(text.strip().upper())
            if match:
                return match.group(1), match.group(2).zfill(8)
        raise UserError(_(
            "No se pudo obtener serie y correlativo de «%s». Use un diario con «Usar documentos» "
            "(l10n_latam) y numeración tipo F001-00000001 / B001-00000001.", self.name))

    def _sunat_check_before_send(self):
        self.ensure_one()
        if self.move_type not in ("out_invoice", "out_refund") or self.state != "posted":
            raise UserError(_("Solo se envían facturas, boletas y notas de cliente publicadas."))
        if self.sunat_doc_type == "NV":
            raise UserError(_("La nota de venta es un documento interno: no se envía a SUNAT."))
        if self.sunat_doc_type == "07" and not self.reversed_entry_id:
            raise UserError(_("La nota de crédito debe originarse de la factura/boleta que modifica "
                              "(use «Añadir nota de crédito» sobre el comprobante original)."))
        if self.sunat_doc_type == "08" and not self.debit_origin_id:
            raise UserError(_("La nota de débito debe originarse de la factura/boleta que modifica "
                              "(use «Añadir nota de débito»)."))
        if self.sunat_doc_type == "01" and len((self.partner_id.vat or "").strip()) != 11:
            raise UserError(_("La factura requiere cliente con RUC de 11 dígitos."))
        if not self.partner_id:
            raise UserError(_("Falta el cliente."))

    def action_send_sunat(self):
        for move in self:
            move._sunat_check_before_send()
            if self.env["sunat.document"].search_count(
                    [("move_id", "=", move.id), ("state", "=", "accepted")]):
                raise UserError(_("Este comprobante ya fue aceptado por SUNAT."))
            self.env["sunat.document"].create({"move_id": move.id}).action_send()
        return True

    def action_view_sunat_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Envíos SUNAT"),
            "res_model": "sunat.document", "view_mode": "list,form",
            "domain": [("move_id", "=", self.id)],
        }

    def action_print_nota_venta(self):
        return self.env.ref("l10n_pe_sunat_beta.action_report_nota_venta").report_action(self)

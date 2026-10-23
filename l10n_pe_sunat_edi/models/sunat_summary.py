import base64
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_pe_sunat_beta.services import signer, soap_client

from ..services import summary_builder

_logger = logging.getLogger(__name__)
MAX_LINES = 500


class SunatSummary(models.Model):
    _name = "sunat.summary"
    _description = "Resumen diario de boletas / Comunicación de baja"
    _order = "id desc"

    kind = fields.Selection(
        [("RC", "Resumen diario de boletas"), ("RA", "Comunicación de baja")],
        string="Tipo", required=True, default="RC")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    issue_date = fields.Date(string="Fecha de generación", required=True, default=fields.Date.context_today)
    reference_date = fields.Date(string="Fecha de los comprobantes", required=True)
    seq = fields.Integer(string="Correlativo", readonly=True, copy=False)
    name = fields.Char(compute="_compute_name", store=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("sent", "Enviado (ticket)"), ("accepted", "Aceptado"),
         ("rejected", "Rechazado"), ("error", "Error")],
        default="draft", readonly=True, copy=False)
    line_ids = fields.One2many("sunat.summary.line", "summary_id", string="Comprobantes")
    ticket = fields.Char(readonly=True, copy=False)
    response_code = fields.Char(readonly=True, copy=False)
    response_message = fields.Text(string="Mensaje SUNAT", readonly=True, copy=False)
    xml_file = fields.Binary(string="XML firmado", attachment=True, readonly=True, copy=False)
    zip_file = fields.Binary(string="ZIP enviado", attachment=True, readonly=True, copy=False)
    cdr_file = fields.Binary(string="CDR (ZIP)", attachment=True, readonly=True, copy=False)
    sent_date = fields.Datetime(readonly=True, copy=False)

    @api.depends("kind", "issue_date", "seq")
    def _compute_name(self):
        for rec in self:
            if rec.issue_date and rec.seq:
                rec.name = "%s-%s-%s" % (rec.kind, rec.issue_date.strftime("%Y%m%d"), rec.seq)
            else:
                rec.name = _("Nuevo")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            same_day = self.search_count([
                ("company_id", "=", rec.company_id.id), ("kind", "=", rec.kind),
                ("issue_date", "=", rec.issue_date), ("id", "!=", rec.id)])
            rec.seq = same_day + 1
        return records

    # ------------------------------------------------------------------
    @api.model
    def _pending_boletas(self, company, date=None, moves=None):
        domain = [("company_id", "=", company.id), ("state", "=", "posted"),
                  ("move_type", "=", "out_invoice"), ("sunat_doc_type", "=", "03")]
        if date:
            domain.append(("invoice_date", "=", date))
        found = moves if moves is not None else self.env["account.move"].search(domain)
        in_summary = self.env["sunat.summary.line"].search([
            ("move_id", "in", found.ids), ("condition", "=", "1"),
            ("summary_id.state", "in", ("draft", "sent", "accepted"))]).mapped("move_id")
        accepted = found.filtered(lambda m: m.sunat_document_ids.filtered(lambda d: d.state == "accepted"))
        return found - in_summary - accepted

    @api.model
    def _create_rc(self, company, date, moves):
        summaries = self.browse()
        moves = moves.sorted("name")
        for i in range(0, len(moves), MAX_LINES):
            chunk = moves[i:i + MAX_LINES]
            summaries |= self.create({
                "kind": "RC", "company_id": company.id, "reference_date": date,
                "line_ids": [(0, 0, {"move_id": m.id, "condition": "1"}) for m in chunk],
            })
        return summaries

    @api.model
    def _send_for_moves(self, moves):
        """Incluye las boletas en resúmenes diarios y los envía."""
        summaries = self.browse()
        for company in moves.mapped("company_id"):
            for date in sorted(set(moves.filtered(lambda m: m.company_id == company).mapped("invoice_date"))):
                day_moves = moves.filtered(lambda m: m.company_id == company and m.invoice_date == date)
                pending = self._pending_boletas(company, moves=day_moves)
                if pending:
                    summaries |= self._create_rc(company, date, pending)
        summaries.action_send()
        return summaries

    @api.model
    def _void_move(self, move, reason):
        if not move.sunat_document_ids.filtered(lambda d: d.state == "accepted"):
            raise UserError(_("Solo se puede dar de baja un comprobante aceptado por SUNAT."))
        if move.sunat_voided:
            raise UserError(_("Este comprobante ya fue dado de baja."))
        kind = "RC" if move.sunat_doc_type == "03" else "RA"
        summary = self.create({
            "kind": kind, "company_id": move.company_id.id, "reference_date": move.invoice_date,
            "line_ids": [(0, 0, {"move_id": move.id, "condition": "3", "reason": reason})],
        })
        summary.action_send()
        return summary

    # ------------------------------------------------------------------
    def _validate(self):
        self.ensure_one()
        company = self.company_id
        if not self.line_ids:
            raise UserError(_("El documento no tiene comprobantes."))
        if len(self.line_ids) > MAX_LINES:
            raise UserError(_("Máximo %s comprobantes por documento.") % MAX_LINES)
        if not company.sunat_cert:
            raise UserError(_("Falta el certificado digital en la compañía."))
        types = set(self.line_ids.mapped("move_id.sunat_doc_type"))
        if self.kind == "RC" and types - {"03"}:
            raise UserError(_("El resumen diario solo admite boletas (03)."))
        if self.kind == "RA" and types - {"01", "07", "08"}:
            raise UserError(_("La comunicación de baja solo admite facturas y notas (01, 07, 08)."))
        dates = set(self.line_ids.mapped("move_id.invoice_date"))
        if dates != {self.reference_date}:
            raise UserError(_("Todos los comprobantes deben tener fecha de emisión %s.") % self.reference_date)

    def action_send(self):
        for summ in self:
            summ._validate()
            company = summ.company_id
            try:
                xml = (summary_builder.build_summary(summ) if summ.kind == "RC"
                       else summary_builder.build_voided(summ))
                xml = signer.sign_xml(xml, base64.b64decode(company.sunat_cert), company.sunat_cert_password)
                base = "%s-%s" % (company.vat, summ.name)
                zip_bytes = soap_client.make_zip(base + ".xml", xml)
                user = "%s%s" % (company.vat, company.sunat_sol_user)
                ticket = soap_client.send_summary(
                    company._sunat_endpoint(), user, company.sunat_sol_password, base + ".zip", zip_bytes)
                summ.write({"xml_file": base64.b64encode(xml), "zip_file": base64.b64encode(zip_bytes),
                            "ticket": ticket, "state": "sent", "sent_date": fields.Datetime.now(),
                            "response_message": False})
                summ._fetch_status()
            except soap_client.SunatError as e:
                summ.write({"state": "error", "response_code": e.code, "response_message": e.message})
            except Exception as e:  # noqa: BLE001
                _logger.exception("Error enviando %s", summ.name)
                summ.write({"state": "error", "response_message": str(e)})
        return True

    def _fetch_status(self):
        self.ensure_one()
        company = self.company_id
        user = "%s%s" % (company.vat, company.sunat_sol_user)
        status, cdr = soap_client.get_status(
            company._sunat_endpoint(), user, company.sunat_sol_password, self.ticket)
        if status in ("0", "99") and cdr:
            code, desc = soap_client.parse_cdr(cdr)
            ok = status == "0" and code == "0"
            self.write({"cdr_file": base64.b64encode(cdr), "response_code": code, "response_message": desc,
                        "state": "accepted" if ok else "rejected"})
            if ok:
                self._on_accepted()
        elif status == "99":
            self.write({"state": "rejected", "response_code": "99",
                        "response_message": _("SUNAT rechazó el documento (sin CDR).")})
        # 98 = en proceso: se mantiene "sent"

    def _on_accepted(self):
        self.ensure_one()
        for line in self.line_ids:
            move = line.move_id
            if line.condition == "1":
                self.env["sunat.document"].create({
                    "move_id": move.id, "name": "%s-%s" % (self.company_id.vat, self.name),
                    "env": self.company_id.sunat_env, "state": "accepted", "summary_id": self.id,
                    "response_code": "0", "cdr_file": self.cdr_file, "sent_date": self.sent_date,
                    "response_message": _("Aceptada mediante %s", self.name)})
            else:
                move.sunat_voided = True

    def action_check_ticket(self):
        for summ in self.filtered("ticket"):
            try:
                summ._fetch_status()
            except soap_client.SunatError as e:
                raise UserError(str(e))
        return True

    def action_reset_draft(self):
        self.filtered(lambda s: s.state in ("error", "rejected")).write({"state": "draft"})

    @api.model
    def _cron_check_tickets(self):
        for summ in self.search([("state", "=", "sent"), ("ticket", "!=", False)], limit=50):
            try:
                summ._fetch_status()
            except Exception:  # noqa: BLE001
                _logger.exception("Resumen %s: error consultando ticket", summ.name)

    @api.model
    def _cron_daily_summary(self):
        """Genera y envía los resúmenes de boletas de los últimos 7 días."""
        today = fields.Date.context_today(self)
        companies = self.env["res.company"].search(
            [("sunat_boleta_mode", "=", "summary"), ("sunat_auto_send", "!=", "off")])
        for company in companies:
            for back in range(7):
                date = today - timedelta(days=back)
                pending = self._pending_boletas(company, date=date)
                if pending:
                    self._create_rc(company, date, pending).action_send()


class SunatSummaryLine(models.Model):
    _name = "sunat.summary.line"
    _description = "Línea de resumen / baja SUNAT"

    summary_id = fields.Many2one("sunat.summary", required=True, ondelete="cascade")
    move_id = fields.Many2one("account.move", string="Comprobante", required=True)
    condition = fields.Selection([("1", "Adicionar"), ("3", "Anular / dar de baja")],
                                 string="Condición", default="1", required=True)
    reason = fields.Char(string="Motivo de baja")

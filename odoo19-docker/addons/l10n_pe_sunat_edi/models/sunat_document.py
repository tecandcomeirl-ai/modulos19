import base64
import logging

from lxml import etree

from odoo import _, fields, models

_logger = logging.getLogger(__name__)
NS_DS = "http://www.w3.org/2000/09/xmldsig#"


class SunatDocument(models.Model):
    _inherit = "sunat.document"

    summary_id = fields.Many2one("sunat.summary", string="Resumen RC", readonly=True)
    mail_sent = fields.Boolean(string="Correo enviado", readonly=True, copy=False)
    digest_value = fields.Char(string="Hash (DigestValue)", compute="_compute_digest_value")

    def _compute_digest_value(self):
        for doc in self:
            value = False
            if doc.xml_file:
                try:
                    root = etree.fromstring(base64.b64decode(doc.xml_file))
                    node = root.find(".//{%s}DigestValue" % NS_DS)
                    value = node.text if node is not None else False
                except Exception:  # noqa: BLE001
                    value = False
            doc.digest_value = value

    def action_send(self):
        res = super().action_send()
        for doc in self.filtered(lambda d: d.state == "accepted" and not d.mail_sent):
            if doc.company_id.sunat_auto_mail:
                doc._edi_send_mail()
        return res

    def _edi_send_mail(self):
        """Envía PDF + XML + CDR al cliente. Nunca bloquea el flujo de facturación."""
        self.ensure_one()
        move = self.move_id
        email = move.partner_id.email
        if not email:
            return False
        try:
            pdf, _ext = self.env["ir.actions.report"]._render_qweb_pdf(
                "l10n_pe_sunat_edi.action_report_cpe", [move.id])
            files = [(self.name + ".pdf", pdf)]
            if self.xml_file:
                files.append((self.name + ".xml", base64.b64decode(self.xml_file)))
            if self.cdr_file:
                files.append(("R-" + self.name + ".zip", base64.b64decode(self.cdr_file)))
            attachments = self.env["ir.attachment"]
            for fname, data in files:
                attachments |= self.env["ir.attachment"].create({
                    "name": fname, "datas": base64.b64encode(data),
                    "res_model": "account.move", "res_id": move.id})
            body = _(
                "<p>Estimado cliente,</p><p>Adjuntamos su comprobante electrónico <b>%(num)s</b> "
                "emitido por %(company)s, aceptado por SUNAT. Incluye la representación impresa (PDF), "
                "el XML firmado y la constancia de recepción (CDR).</p>",
                num=move.sunat_number or move.name, company=move.company_id.name)
            self.env["mail.mail"].sudo().create({
                "subject": _("%(company)s: comprobante electrónico %(num)s",
                             company=move.company_id.name, num=move.sunat_number or move.name),
                "body_html": body, "email_to": email,
                "email_from": move.company_id.email or self.env.user.email_formatted,
                "attachment_ids": [(6, 0, attachments.ids)],
                "model": "account.move", "res_id": move.id, "auto_delete": False,
            }).send()
            self.mail_sent = True
        except Exception:  # noqa: BLE001
            _logger.exception("No se pudo enviar el correo del comprobante %s", self.name)
            return False
        return True

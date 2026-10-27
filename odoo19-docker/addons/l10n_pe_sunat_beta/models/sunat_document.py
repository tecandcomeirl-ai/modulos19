import base64
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..services import signer, soap_client, ubl_builder

_logger = logging.getLogger(__name__)


class SunatDocument(models.Model):
    _name = "sunat.document"
    _description = "Comprobante enviado a SUNAT"
    _order = "id desc"

    name = fields.Char(string="Archivo", readonly=True)
    move_id = fields.Many2one("account.move", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="move_id.company_id", store=True)
    doc_type = fields.Selection(related="move_id.sunat_doc_type", store=True, string="Tipo")
    env = fields.Selection([("beta", "Beta"), ("prod", "Producción")], readonly=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("signed", "Firmado"), ("accepted", "Aceptado"),
         ("rejected", "Rechazado"), ("error", "Error")],
        default="draft", readonly=True,
    )
    xml_file = fields.Binary(string="XML firmado", attachment=True, readonly=True)
    zip_file = fields.Binary(string="ZIP enviado", attachment=True, readonly=True)
    cdr_file = fields.Binary(string="CDR recibido (ZIP)", attachment=True, readonly=True)
    response_code = fields.Char(string="Código de respuesta", readonly=True)
    response_message = fields.Text(string="Mensaje SUNAT", readonly=True)
    ticket = fields.Char(readonly=True)
    sent_date = fields.Datetime(readonly=True)

    # ------------------------------------------------------------------
    def _credentials(self):
        self.ensure_one()
        company = self.company_id
        if not (company.vat and company.sunat_sol_user and company.sunat_sol_password):
            raise UserError(_("Configure RUC, usuario y clave SOL en la compañía."))
        if not company.sunat_cert:
            raise UserError(_("Cargue el certificado digital (.pfx) en la compañía."))
        return "%s%s" % (company.vat, company.sunat_sol_user), company.sunat_sol_password

    def _original_ref(self):
        """Datos del comprobante modificado por una NC/ND."""
        move = self.move_id
        origin = move.reversed_entry_id if move.sunat_doc_type == "07" else move.debit_origin_id
        if not origin:
            raise UserError(_("No se encontró el comprobante original de la nota."))
        if origin.sunat_doc_type not in ("01", "03"):
            raise UserError(_("El comprobante original debe ser Factura o Boleta electrónica."))
        series, number = origin._sunat_series_number()
        return {"series": series, "number": number, "doc_type": origin.sunat_doc_type}

    def action_send(self):
        for doc in self:
            move = doc.move_id
            try:
                move._sunat_check_before_send()
                series, number = move._sunat_series_number()
                doc_type = move.sunat_doc_type
                original = doc._original_ref() if doc_type in ("07", "08") else None
                base = "%s-%s-%s-%s" % (move.company_id.vat, doc_type, series, number)
                user, pwd = doc._credentials()
                xml = ubl_builder.build_document(move, doc_type, series, number, original)
                xml = signer.sign_xml(
                    xml, base64.b64decode(move.company_id.sunat_cert),
                    move.company_id.sunat_cert_password)
                zip_bytes = soap_client.make_zip(base + ".xml", xml)
                doc.write({
                    "name": base, "env": move.company_id.sunat_env, "state": "signed",
                    "xml_file": base64.b64encode(xml), "zip_file": base64.b64encode(zip_bytes),
                    "sent_date": fields.Datetime.now(),
                })
                cdr = soap_client.send_bill(
                    move.company_id._sunat_endpoint(), user, pwd, base + ".zip", zip_bytes)
                code, desc = soap_client.parse_cdr(cdr)
                doc.write({
                    "cdr_file": base64.b64encode(cdr),
                    "response_code": code, "response_message": desc,
                    "state": "accepted" if code == "0" else "rejected",
                })
                doc._attach_files(base, xml, cdr)
            except soap_client.SunatError as e:
                doc.write({"state": "error", "response_code": e.code, "response_message": e.message})
            except UserError:
                raise
            except Exception as e:  # noqa: BLE001
                _logger.exception("Error enviando a SUNAT")
                doc.write({"state": "error", "response_message": str(e)})
        return True

    def action_check_ticket(self):
        """Consulta asíncrona (resúmenes / bajas) por ticket y recibe el CDR."""
        for doc in self.filtered("ticket"):
            user, pwd = doc._credentials()
            status, cdr = soap_client.get_status(
                doc.company_id._sunat_endpoint(), user, pwd, doc.ticket)
            if status == "0" and cdr:
                code, desc = soap_client.parse_cdr(cdr)
                doc.write({"cdr_file": base64.b64encode(cdr), "response_code": code,
                           "response_message": desc,
                           "state": "accepted" if code == "0" else "rejected"})
            elif status == "98":
                raise UserError(_("SUNAT aún está procesando el ticket %s.") % doc.ticket)
        return True

    def _attach_files(self, base, xml, cdr):
        att = self.env["ir.attachment"]
        for fname, data in ((base + ".xml", xml), ("R-" + base + ".zip", cdr)):
            att.create({
                "name": fname, "datas": base64.b64encode(data),
                "res_model": "account.move", "res_id": self.move_id.id,
            })

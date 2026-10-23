import base64

from odoo import _, models
from odoo.exceptions import UserError

from odoo.addons.l10n_pe_sunat_beta.services import soap_client

from ..services import consulta_client


class SunatDocument(models.Model):
    _inherit = "sunat.document"

    def action_consult_cdr(self):
        """Recupera el CDR desde SUNAT (billConsultService; disponible solo en producción)."""
        for doc in self:
            if doc.company_id.sunat_env != "prod":
                raise UserError(_("La consulta de CDR por número solo está disponible en producción. "
                                  "En beta el CDR se recibe al enviar el comprobante."))
            user, pwd = doc._credentials()
            series, number = doc.move_id._sunat_series_number()
            try:
                status, message, cdr = consulta_client.get_status_cdr(
                    doc.company_id, user, pwd, doc.company_id.vat, doc.doc_type, series, number)
            except soap_client.SunatError as e:
                raise UserError(str(e))
            vals = {"response_message": message}
            if cdr:
                code, desc = soap_client.parse_cdr(cdr)
                vals.update({"cdr_file": base64.b64encode(cdr), "response_code": code,
                             "response_message": desc, "state": "accepted" if code == "0" else "rejected"})
            doc.write(vals)
        return True

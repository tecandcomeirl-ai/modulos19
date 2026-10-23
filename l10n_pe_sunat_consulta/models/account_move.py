import re

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..services import consulta_client
from ..services.consulta_client import ESTADO_CP

VENDOR_NUM_RE = re.compile(r"([A-Z0-9]{1,4})-(\d{1,8})\s*$")


class AccountMove(models.Model):
    _inherit = "account.move"

    sunat_cp_state = fields.Selection(ESTADO_CP, string="Validez en SUNAT", readonly=True, copy=False)
    sunat_cp_checked = fields.Datetime(string="Última validación SUNAT", readonly=True, copy=False)

    def _sunat_consulta_params(self):
        """(ruc_emisor, codigo, serie, numero, fecha, monto) del comprobante."""
        self.ensure_one()
        if self.move_type in ("out_invoice", "out_refund"):
            if self.sunat_doc_type in (False, "NV"):
                raise UserError(_("Este documento no es un comprobante electrónico SUNAT."))
            series, number = self._sunat_series_number()
            return self.company_id.vat, self.sunat_doc_type, series, number, self.invoice_date, self.amount_total
        if self.move_type in ("in_invoice", "in_refund"):
            code = "01"
            if "l10n_latam_document_type_id" in self._fields and self.l10n_latam_document_type_id:
                code = self.l10n_latam_document_type_id.code or "01"
            elif self.move_type == "in_refund":
                code = "07"
            texts = []
            if "l10n_latam_document_number" in self._fields:
                texts.append(self.l10n_latam_document_number or "")
            texts.append(self.ref or "")
            for text in texts:
                match = VENDOR_NUM_RE.search(text.strip().upper())
                if match:
                    if not self.partner_id.vat:
                        raise UserError(_("El proveedor no tiene RUC."))
                    return (self.partner_id.vat, code, match.group(1), match.group(2),
                            self.invoice_date, self.amount_total)
            raise UserError(_("Indique la referencia del proveedor como SERIE-NÚMERO (ej. F001-123)."))
        raise UserError(_("Tipo de asiento no soportado para consulta."))

    def action_consult_sunat(self):
        self.ensure_one()
        if not self.invoice_date:
            raise UserError(_("Falta la fecha de emisión."))
        ruc, code, series, number, date, amount = self._sunat_consulta_params()
        try:
            res = consulta_client.validar_comprobante(self.company_id, ruc, code, series, number, date, amount)
        except (consulta_client.ConsultaError, Exception) as e:  # noqa: BLE001
            raise UserError(str(e))
        self.write({"sunat_cp_state": res["estado_cp"], "sunat_cp_checked": fields.Datetime.now()})
        self.env["sunat.consulta.log"].create({
            "move_id": self.id, "company_id": self.company_id.id, "doc_code": code, "ruc_emisor": ruc,
            "series": series, "number": number, "issue_date": date, "amount": amount,
            "estado_cp": res["estado_cp"] or False, "estado_ruc": consulta_client.ESTADO_RUC.get(
                res["estado_ruc"], res["estado_ruc"]),
            "cond_domi": consulta_client.COND_DOMI.get(res["cond_domi"], res["cond_domi"]),
            "observaciones": res["observaciones"], "response": res["raw"],
        })
        label = dict(ESTADO_CP).get(res["estado_cp"], res["estado_cp"])
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Consulta SUNAT"), "message": _("Estado del comprobante: %s", label),
                       "type": "success" if res["estado_cp"] in ("1", "3") else "warning", "sticky": False},
        }

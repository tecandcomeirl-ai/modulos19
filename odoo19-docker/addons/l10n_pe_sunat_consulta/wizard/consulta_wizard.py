from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.consulta_log import DOC_CODES
from ..services import consulta_client
from ..services.consulta_client import ESTADO_CP


class SunatConsultaWizard(models.TransientModel):
    _name = "sunat.consulta.wizard"
    _description = "Consulta de validez de comprobante (SUNAT)"

    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    ruc_emisor = fields.Char(string="RUC del emisor", required=True,
                             default=lambda s: s.env.company.vat)
    doc_code = fields.Selection(DOC_CODES, string="Tipo de comprobante", default="01", required=True)
    series = fields.Char(string="Serie", required=True, size=4)
    number = fields.Char(string="Número", required=True)
    issue_date = fields.Date(string="Fecha de emisión", required=True, default=fields.Date.context_today)
    amount = fields.Float(string="Monto total", required=True)

    estado_cp = fields.Selection(ESTADO_CP, string="Estado del comprobante", readonly=True)
    estado_ruc = fields.Char(string="Estado del RUC emisor", readonly=True)
    cond_domi = fields.Char(string="Condición de domicilio", readonly=True)
    observaciones = fields.Text(readonly=True)

    def action_consult(self):
        self.ensure_one()
        try:
            res = consulta_client.validar_comprobante(
                self.company_id, self.ruc_emisor.strip(), self.doc_code,
                self.series.strip().upper(), self.number.strip(), self.issue_date, self.amount)
        except consulta_client.ConsultaError as e:
            raise UserError(str(e))
        except Exception as e:  # noqa: BLE001
            raise UserError(_("Error de conexión con SUNAT: %s") % e)
        ruc_txt = consulta_client.ESTADO_RUC.get(res["estado_ruc"], res["estado_ruc"])
        dom_txt = consulta_client.COND_DOMI.get(res["cond_domi"], res["cond_domi"])
        self.write({"estado_cp": res["estado_cp"] or False, "estado_ruc": ruc_txt,
                    "cond_domi": dom_txt, "observaciones": res["observaciones"]})
        self.env["sunat.consulta.log"].create({
            "company_id": self.company_id.id, "doc_code": self.doc_code, "ruc_emisor": self.ruc_emisor,
            "series": self.series, "number": self.number, "issue_date": self.issue_date,
            "amount": self.amount, "estado_cp": res["estado_cp"] or False, "estado_ruc": ruc_txt,
            "cond_domi": dom_txt, "observaciones": res["observaciones"], "response": res["raw"],
        })
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new"}

import json

from odoo import _, fields, models
from odoo.exceptions import UserError


class ApisPeruLookupWizard(models.TransientModel):
    _name = "apisperu.lookup.wizard"
    _description = "Consultar DNI / RUC (APIsPERU)"

    kind = fields.Selection([("dni", "DNI"), ("ruc", "RUC")], string="Documento", default="dni", required=True)
    number = fields.Char(string="Número", required=True)
    state = fields.Selection([("draft", "Borrador"), ("done", "Consultado")], default="draft")
    result_json = fields.Text(readonly=True)
    result_name = fields.Char(string="Nombre / Razón social", readonly=True)
    result_detail = fields.Text(string="Detalle", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Contacto existente", readonly=True)

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new"}

    def action_lookup(self):
        self.ensure_one()
        service = self.env["apisperu.service"]
        data = service._lookup(self.kind, self.number)
        if self.kind == "dni":
            name = self.env["res.partner"]._apisperu_prepare_vals("dni", data)["name"]
            detail = _("Código de verificación: %s", data["check_digit"] or "-")
        else:
            name = data["name"]
            lines = [_("Estado: %s", data["status"] or "-"), _("Condición: %s", data["condition"] or "-"),
                     _("Dirección: %s", data["address"] or "-"),
                     "%s / %s / %s" % (data["department"], data["province"], data["district"])]
            if data["trade_name"]:
                lines.insert(0, _("Nombre comercial: %s", data["trade_name"]))
            detail = "\n".join(lines)
        partner = self.env["res.partner"].search([("vat", "ilike", data["document"])], limit=1)
        self.write({"state": "done", "result_json": json.dumps(data), "result_name": name,
                    "result_detail": detail, "partner_id": partner.id})
        return self._reopen()

    def _data(self):
        if not self.result_json:
            raise UserError(_("Primero realice la consulta."))
        return json.loads(self.result_json)

    def action_create_partner(self):
        self.ensure_one()
        vals = self.env["res.partner"]._apisperu_prepare_vals(self.kind, self._data())
        partner = self.env["res.partner"].create(vals)
        return {"type": "ir.actions.act_window", "res_model": "res.partner", "res_id": partner.id,
                "view_mode": "form", "target": "current"}

    def action_update_partner(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("No hay un contacto existente con ese documento."))
        self.partner_id._apisperu_apply(self.kind, self._data())
        return {"type": "ir.actions.act_window", "res_model": "res.partner", "res_id": self.partner_id.id,
                "view_mode": "form", "target": "current"}

from odoo import fields, models


class SunatVoidWizard(models.TransientModel):
    _name = "sunat.void.wizard"
    _description = "Dar de baja un comprobante en SUNAT"

    move_id = fields.Many2one("account.move", required=True, readonly=True)
    reason = fields.Char(string="Motivo de la baja", required=True, default="ERROR EN LA EMISION")

    def action_confirm(self):
        self.ensure_one()
        summary = self.env["sunat.summary"]._void_move(self.move_id, self.reason)
        return {"type": "ir.actions.act_window", "res_model": "sunat.summary",
                "res_id": summary.id, "view_mode": "form"}

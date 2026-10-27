from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    sunat_detraction_code_id = fields.Many2one(
        "sunat.detraction.code", string="Código de detracción",
        compute="_compute_sunat_detraction_code", store=True, readonly=False, copy=True)
    sunat_detraction_rate = fields.Float(
        string="Tasa detracción (%)", compute="_compute_sunat_detraction", store=True, digits=(5, 2))
    sunat_detraction_amount = fields.Float(
        string="Monto detracción (S/)", compute="_compute_sunat_detraction", store=True, digits=(12, 2))
    sunat_detraction_deposit_date = fields.Date(string="Fecha de constancia de depósito", copy=False)
    sunat_detraction_deposit_number = fields.Char(string="N.° constancia de depósito", copy=False)

    @api.depends("invoice_line_ids.product_id", "sunat_doc_type", "move_type")
    def _compute_sunat_detraction_code(self):
        for move in self:
            code = False
            if move.move_type == "out_invoice" and move.sunat_doc_type in (False, "01"):
                for line in move.invoice_line_ids:
                    if line.display_type == "product" and line.product_id.sunat_detraction_code_id:
                        code = line.product_id.sunat_detraction_code_id
                        break
            move.sunat_detraction_code_id = code or move.sunat_detraction_code_id

    @api.depends("sunat_detraction_code_id", "amount_total", "currency_id", "invoice_date", "company_id")
    def _compute_sunat_detraction(self):
        for move in self:
            code = move.sunat_detraction_code_id
            rate = amount = 0.0
            if code:
                total_pen = move.amount_total
                company = move.company_id
                if move.currency_id and company.currency_id and move.currency_id != company.currency_id:
                    total_pen = move.currency_id._convert(
                        move.amount_total, company.currency_id, company,
                        move.invoice_date or fields.Date.context_today(move))
                if total_pen > code.min_amount:
                    rate = code.rate
                    amount = total_pen * rate / 100.0
                    if company.sunat_detraction_round:
                        amount = float(int(amount + 0.5))
            move.sunat_detraction_rate = rate
            move.sunat_detraction_amount = amount

    def _sunat_check_before_send(self):
        super()._sunat_check_before_send()
        for move in self:
            if move.sunat_detraction_code_id and move.sunat_detraction_amount:
                if move.sunat_doc_type != "01":
                    raise UserError(_("La detracción solo se informa en facturas (01)."))
                if not move.company_id.sunat_detraction_account:
                    raise UserError(_("Configure la cuenta de detracciones del Banco de la Nación "
                                      "en la compañía (pestaña SUNAT)."))

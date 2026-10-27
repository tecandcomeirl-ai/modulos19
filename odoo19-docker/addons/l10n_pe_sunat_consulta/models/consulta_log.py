from odoo import fields, models

from ..services.consulta_client import ESTADO_CP

DOC_CODES = [
    ("01", "Factura"), ("03", "Boleta de venta"), ("04", "Liquidación de compra"),
    ("07", "Nota de crédito"), ("08", "Nota de débito"),
    ("R1", "Recibo por honorarios"), ("R7", "Nota de crédito de recibos"),
]


class SunatConsultaLog(models.Model):
    _name = "sunat.consulta.log"
    _description = "Historial de consultas de comprobantes a SUNAT"
    _order = "id desc"

    date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, readonly=True)
    user_id = fields.Many2one("res.users", default=lambda s: s.env.user, readonly=True)
    move_id = fields.Many2one("account.move", string="Asiento", readonly=True, ondelete="set null")
    doc_code = fields.Selection(DOC_CODES, string="Tipo", readonly=True)
    ruc_emisor = fields.Char(string="RUC emisor", readonly=True)
    series = fields.Char(string="Serie", readonly=True)
    number = fields.Char(string="Número", readonly=True)
    issue_date = fields.Date(string="Fecha emisión", readonly=True)
    amount = fields.Float(string="Monto", readonly=True)
    estado_cp = fields.Selection(ESTADO_CP, string="Estado CPE", readonly=True)
    estado_ruc = fields.Char(string="Estado RUC", readonly=True)
    cond_domi = fields.Char(string="Condición domicilio", readonly=True)
    observaciones = fields.Text(readonly=True)
    response = fields.Text(string="Respuesta JSON", readonly=True)

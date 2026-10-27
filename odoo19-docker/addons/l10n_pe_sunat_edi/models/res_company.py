from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sunat_auto_send = fields.Selection(
        [("off", "Manual"), ("post", "Al publicar"), ("cron", "Programado (cron)")],
        string="Envío a SUNAT", default="off", required=True,
        help="Manual: botón en cada comprobante. Al publicar: se envía al validar la factura. "
             "Programado: un cron envía/reintenta cada 15 minutos.")
    sunat_boleta_mode = fields.Selection(
        [("individual", "Individual (sendBill)"), ("summary", "Resumen diario (RC)")],
        string="Envío de boletas", default="individual", required=True)
    sunat_auto_mail = fields.Boolean(
        string="Enviar por correo al ser aceptado",
        help="Envía al cliente el PDF, el XML y el CDR cuando SUNAT acepta el comprobante.")
    sunat_max_attempts = fields.Integer(string="Reintentos máximos", default=5)

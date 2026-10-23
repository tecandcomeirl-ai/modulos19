from datetime import datetime

from odoo import api, fields, models

from ..services.client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT


class ResCompany(models.Model):
    _inherit = "res.company"

    apisperu_token = fields.Char(
        string="Token APIsPERU", groups="base.group_system",
        help="Token de acceso. Se obtiene en https://apisperu.com/admin. Solo lo ven los administradores.")
    apisperu_base_url = fields.Char(
        string="URL base de la API", default=DEFAULT_BASE_URL, groups="base.group_system",
        help="Normalmente no se cambia. Solo si APIsPERU le indica otra dirección.")
    apisperu_timeout = fields.Integer(string="Tiempo de espera (s)", default=DEFAULT_TIMEOUT, groups="base.group_system")
    apisperu_name_format = fields.Selection(
        [("last_first", "APELLIDOS NOMBRES (formato SUNAT)"), ("first_last", "NOMBRES APELLIDOS")],
        string="Formato del nombre", default="last_first", required=True)
    apisperu_auto_fill = fields.Boolean(
        string="Completar al escribir el DNI/RUC", default=True,
        help="Al escribir el DNI o RUC en un contacto NUEVO sin nombre, consulta la API y completa el nombre.")
    apisperu_queries_month = fields.Integer(
        string="Consultas este mes", compute="_compute_apisperu_queries_month", groups="base.group_system")

    @api.depends_context("uid")
    def _compute_apisperu_queries_month(self):
        first = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for company in self:
            company.apisperu_queries_month = self.env["apisperu.log"].sudo().search_count([
                ("company_id", "=", company.id), ("date", ">=", first)])

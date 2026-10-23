import logging
import time

from odoo import SUPERUSER_ID, _, api, models
from odoo.exceptions import UserError

from ..services import client

_logger = logging.getLogger(__name__)


class ApisPeruService(models.AbstractModel):
    _name = "apisperu.service"
    _description = "Servicio de consulta APIsPERU"

    @api.model
    def _has_token(self, company=None):
        return bool((company or self.env.company).sudo().apisperu_token)

    @api.model
    def _write_log(self, company, kind, number, success, error=None, duration_ms=0):
        """Registra la consulta en un cursor aparte para que persista aunque la transacción se revierta."""
        try:
            with self.env.registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env["apisperu.log"].create({
                    "company_id": company.id, "user_id": self.env.uid, "kind": kind,
                    "masked_number": client.mask(client.digits(number)), "success": success,
                    "error_code": error.code if error else False,
                    "message": (error.message[:200] if error else False), "duration_ms": duration_ms,
                })
        except Exception:  # noqa: BLE001 - el historial nunca debe impedir la consulta
            _logger.warning("APIsPERU: no se pudo registrar el historial de consultas", exc_info=False)

    @api.model
    def _lookup(self, kind, number, company=None):
        company = (company or self.env.company).sudo()
        func = client.lookup_dni if kind == "dni" else client.lookup_ruc
        started = time.monotonic()
        error = None
        data = None
        try:
            data = func(number, company.apisperu_token, company.apisperu_base_url or client.DEFAULT_BASE_URL,
                        company.apisperu_timeout or client.DEFAULT_TIMEOUT)
        except client.ApisPeruError as exc:
            error = exc
        elapsed = int((time.monotonic() - started) * 1000)
        # Las validaciones locales (número mal escrito, sin token) no consumen consulta: no se registran.
        if error is None or error.code not in ("invalid", "config"):
            self._write_log(company, kind, number, error is None, error, elapsed)
        if error:
            raise UserError(error.message)
        return data

    @api.model
    def lookup_dni(self, number, company=None):
        return self._lookup("dni", number, company)

    @api.model
    def lookup_ruc(self, number, company=None):
        return self._lookup("ruc", number, company)

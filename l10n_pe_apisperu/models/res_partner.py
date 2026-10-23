from odoo import _, api, models
from odoo.exceptions import UserError

from ..services import client

BULK_LIMIT = 50


class ResPartner(models.Model):
    _inherit = "res.partner"

    # ------------------------------------------------------------------ utilidades
    def _apisperu_doc_info(self):
        """('dni'|'ruc'|False, número) según el tipo de identificación (l10n_latam) o la longitud."""
        self.ensure_one()
        number = client.digits(self.vat)
        code = False
        if "l10n_latam_identification_type_id" in self._fields:
            code = getattr(self.l10n_latam_identification_type_id, "l10n_pe_vat_code", False)
        if code == "1" or (not code and len(number) == 8):
            return "dni", number
        if code == "6" or (not code and len(number) == 11):
            return "ruc", number
        return False, number

    @api.model
    def _apisperu_prepare_vals(self, kind, data, company=None):
        company = company or self.env.company
        vals = {"vat": data["document"]}
        if kind == "dni":
            vals.update(name=client.build_full_name(data, company.apisperu_name_format), is_company=False)
        else:
            vals.update(name=data["name"], is_company=data["document"].startswith("20"))
            if data.get("address"):
                vals["street"] = data["address"]
            if data.get("district"):
                vals["city"] = data["district"]
        peru = self.env.ref("base.pe", raise_if_not_found=False)
        if peru:
            vals["country_id"] = peru.id
            if kind == "ruc" and data.get("department"):
                state = self.env["res.country.state"].search(
                    [("country_id", "=", peru.id), ("name", "=ilike", data["department"])], limit=1)
                if state:
                    vals["state_id"] = state.id
        if "l10n_latam_identification_type_id" in self._fields:
            ident = self.env["l10n_latam.identification.type"].search(
                [("l10n_pe_vat_code", "=", "1" if kind == "dni" else "6")], limit=1)
            if ident:
                vals["l10n_latam_identification_type_id"] = ident.id
        return vals

    def _apisperu_apply(self, kind, data):
        """Actualiza el contacto: el nombre siempre; la dirección solo si está vacía."""
        self.ensure_one()
        vals = self._apisperu_prepare_vals(kind, data, self.company_id or None)
        for key in ("street", "city", "state_id", "country_id"):
            if self[key]:
                vals.pop(key, None)
        self.write(vals)
        return vals

    # ------------------------------------------------------------------ botón del contacto
    def action_apisperu_lookup(self):
        self.ensure_one()
        kind, number = self._apisperu_doc_info()
        if not kind:
            raise UserError(_("Escriba un DNI (8 dígitos) o un RUC (11 dígitos) en el campo de identificación."))
        data = self.env["apisperu.service"]._lookup(kind, number, self.company_id or None)
        self._apisperu_apply(kind, data)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Consulta APIsPERU"), "type": "success", "sticky": False,
                       "message": _("Datos actualizados: %s", self.name)},
        }

    # ------------------------------------------------------------------ contacto nuevo: completar al escribir
    @api.onchange("vat")
    def _onchange_vat_apisperu(self):
        company = self.company_id or self.env.company
        if not self.vat or self.name or not company.apisperu_auto_fill:
            return
        if not self.env["apisperu.service"]._has_token(company):
            return  # sin token configurado no se molesta al usuario
        kind, number = self._apisperu_doc_info()
        if not kind:
            return
        try:
            data = self.env["apisperu.service"]._lookup(kind, number, company)
        except UserError as exc:
            return {"warning": {"title": _("Consulta DNI/RUC"), "message": exc.args[0]}}
        for key, value in self._apisperu_prepare_vals(kind, data, company).items():
            if key != "vat":
                self[key] = value

    # ------------------------------------------------------------------ acción masiva
    def action_apisperu_fill_names(self):
        """Completa el nombre de contactos cuyo nombre está vacío o es solo el número de DNI (máx. 50)."""
        filled, skipped, error = 0, 0, False
        for partner in self[:BULK_LIMIT]:
            kind, number = partner._apisperu_doc_info()
            current = (partner.name or "").strip()
            if kind != "dni" or (current and client.digits(current) != number):
                skipped += 1
                continue
            try:
                data = self.env["apisperu.service"]._lookup("dni", number, partner.company_id or None)
            except UserError as exc:
                error = exc.args[0]
                break  # token inválido, límite o caída: no tiene sentido seguir gastando consultas
            partner._apisperu_apply("dni", data)
            filled += 1
        message = _("Completados: %(ok)s · Omitidos: %(skip)s", ok=filled, skip=skipped)
        if len(self) > BULK_LIMIT:
            message += _(" · Solo se procesan %s por vez.", BULK_LIMIT)
        if error:
            message += _(" · Se detuvo: %s", error)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Consulta DNI"), "message": message,
                       "type": "warning" if error else "success", "sticky": bool(error)},
        }
